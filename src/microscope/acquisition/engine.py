# src/microscope/acquisition/engine.py
"""
Custom MDA engine for PLogic-driven SPIM acquisitions.
Manages the acquisition lifecycle, frame buffering, and scrubbing.
"""

import logging

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from qtpy.QtCore import QMetaObject, Qt, QThread
from useq import (
    AnyTimePlan,
    AnyZPlan,
    MDAEvent,
    MDASequence,
    MultiPhaseTimePlan,
    TIntervalLoops,
    ZAboveBelow,
    ZRangeAround,
)

from microscope.acquisition.worker import AcquisitionWorker
from microscope.hardware import (
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
    trigger_spim_scan_acquisition,
)
from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


class PLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self, mmc: CMMCorePlus, hw_constants: HardwareConstants):
        super().__init__(mmc)
        self._mmc = mmc
        self.HW = hw_constants
        self._worker: AcquisitionWorker | None = None
        self._thread: QThread | None = None
        self._frame_buffer: dict = {}
        self._sequence: MDASequence | None = None
        self._original_autoshutter: bool = False

    def run(self, sequence: MDASequence) -> None:
        """Run an MDA sequence, handling setup, execution, and cleanup."""
        self._frame_buffer.clear()
        self._sequence = sequence
        self._original_autoshutter = self._mmc.getAutoShutter()

        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})

            if not self._setup_hardware(sequence):
                # Ensure we clean up even if setup fails
                self._cleanup_hardware(sequence)
                return

            # The total number of images is simply the total length of the sequence iterable
            total_images = len(list(sequence))

            self._worker = AcquisitionWorker(self._mmc, sequence, self.HW, total_images)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            self._worker.frameReady.connect(self._on_frame_ready, Qt.ConnectionType.QueuedConnection)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished, Qt.ConnectionType.QueuedConnection)
            self._thread.started.connect(self._start_worker_and_hardware)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine")
            self._mmc.run_mda(sequence)

    def _start_worker_and_hardware(self):
        """Trigger hardware from the main thread, then start the worker's loop."""
        if not self._worker:
            return

        # These calls now safely execute in the main thread.
        self._mmc.startSequenceAcquisition(self.HW.camera_a_label, self._worker.total_images, 0, True)
        trigger_spim_scan_acquisition(self._mmc, self.HW)

        # Asynchronously invoke the worker's run method in its own thread.
        QMetaObject.invokeMethod(
            self._worker,
            b"run",  # Method name must be bytes
            Qt.ConnectionType.QueuedConnection,
        )

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            return current_focus_device == self.HW.piezo_a_label
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _setup_hardware(self, sequence: MDASequence) -> bool:
        """Configure all hardware for the sequence. Runs in the main thread."""
        try:
            num_z = sequence.shape[sequence.axis_order.index("z")]
        except ValueError:
            logger.error("Sequence must have a 'z' axis for PLogic acquisition.")
            return False

        z_plan = sequence.z_plan
        if not z_plan:
            logger.error("PLogic acquisition requires a Z-plan, but it is missing.")
            return False

        # A T-plan is optional; if not present, we default to a single time point.
        try:
            num_t = sequence.shape[sequence.axis_order.index("t")]
        except ValueError:
            logger.info("No 't' axis found in sequence, defaulting to a single timepoint.")
            num_t = 1

        # Get exposure from the MDA sequence; fall back to the core setting if not specified.
        exposure_ms = self._mmc.getExposure()
        if sequence.channels and sequence.channels[0].exposure is not None:
            exposure_ms = sequence.channels[0].exposure
            logger.info(f"Using exposure from MDA sequence: {exposure_ms} ms")

        interval_s = self._get_time_interval_s(sequence.time_plan)
        scan_duration_s = (num_z * exposure_ms) / 1000.0
        repeat_delay_ms = max(0, (interval_s - scan_duration_s) * 1000.0)

        total_images = len(list(sequence))
        logger.info(
            "Starting hardware-timed series: %d images planned (%d timepoints, %d z-slices).",
            total_images,
            num_t,
            num_z,
        )

        self._mmc.setAutoShutter(False)
        if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
            return False

        # Update the existing AcquisitionSettings object from the hardware model
        # with values from the current MDA sequence.
        settings = self.HW.acquisition
        settings.num_slices = num_z
        settings.step_size_um = self._get_z_step_size(z_plan)
        settings.camera_exposure_ms = exposure_ms
        settings.laser_trig_duration_ms = exposure_ms  # Ensure laser pulse matches camera

        configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

        # Calculate galvo amplitude and update the settings object.
        # The default is loaded from the config file.
        try:
            z_positions = list(z_plan)
            if len(z_positions) > 1:
                z_range = max(z_positions) - min(z_positions)
                settings.galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg
                logger.info(
                    "Calculated galvo amplitude of %.4f deg for a Z-range of %.2f um.",
                    settings.galvo_amplitude_deg,
                    z_range,
                )
        except TypeError:
            logger.warning("Z-plan is not iterable, cannot calculate galvo amplitude from range.")

        configure_galvo_for_spim_scan(
            self._mmc,
            settings,
            num_repeats=num_t,
            repeat_delay_ms=repeat_delay_ms,
            hw=self.HW,
        )
        return True

    def _on_frame_ready(self, frame: object, event: MDAEvent, meta: dict) -> None:
        """Slot to handle the frameReady signal from the worker."""
        key = tuple(event.index.get(k, 0) for k in ("t", "p", "z", "c"))
        self._frame_buffer[key] = (frame, event, meta)
        self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def set_displayed_slice(self, t: int, z: int) -> None:
        """Request a specific t- and z-slice to be displayed."""
        lookup_key = (t, 0, z, 0)
        if lookup_key in self._frame_buffer:
            frame, event, meta = self._frame_buffer[lookup_key]
            self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def _cleanup_hardware(self, sequence: MDASequence) -> None:
        """Resets hardware to a safe, idle state after acquisition."""
        logger.info("Cleaning up hardware state...")
        self._mmc.stopSequenceAcquisition()
        set_property(self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger")
        set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
        self._mmc.setAutoShutter(self._original_autoshutter)
        self._mmc.mda.events.sequenceFinished.emit(sequence)

    def _on_acquisition_finished(self, sequence: MDASequence) -> None:
        """Slot to handle the acquisitionFinished signal from the worker."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._cleanup_hardware(sequence)

    def _get_z_step_size(self, z_plan: AnyZPlan) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        if isinstance(z_plan, ZRangeAround | ZAboveBelow):
            return z_plan.step
        try:
            z_positions = list(z_plan)
            if len(z_positions) > 1:
                return abs(z_positions[1] - z_positions[0])
        except TypeError:
            pass
        return 0.0

    def _get_time_interval_s(self, time_plan: AnyTimePlan | None) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0
