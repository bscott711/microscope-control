# src/microscope/acquisition/engine.py
"""
Custom MDA engine for PLogic-driven SPIM acquisitions.
Manages the acquisition lifecycle, frame buffering, and scrubbing.
"""

import logging
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from qtpy.QtCore import Qt, QThread
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

from microscope.acquisition.worker import AcquisitionWorker, TimingParams
from microscope.hardware import (
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
)
from microscope.model.hardware_model import AcquisitionSettings, HardwareConstants

logger = logging.getLogger(__name__)


class PLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self, mmc: CMMCorePlus, hw_constants: HardwareConstants):
        super().__init__(mmc)
        self._mmc = mmc
        self.HW = hw_constants
        self._worker: Optional[AcquisitionWorker] = None
        self._thread: Optional[QThread] = None
        self._frame_buffer: dict = {}

    def run(self, sequence: MDASequence) -> None:
        """Run an MDA sequence, handling setup, execution, and cleanup."""
        self._frame_buffer.clear()
        self._sequence = sequence

        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})

            params = self._calculate_timing_params(sequence)
            if not params or not self._configure_hardware(sequence, params):
                self._mmc.mda.events.sequenceFinished.emit(sequence)
                return

            self._worker = AcquisitionWorker(self._mmc, sequence, self.HW, params)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            self._worker.frameReady.connect(
                self._on_frame_ready, Qt.ConnectionType.QueuedConnection
            )
            self._thread.started.connect(self._worker.run)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine")
            self._mmc.run_mda(sequence)

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            return current_focus_device == self.HW.piezo_a_label
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _calculate_timing_params(self, sequence: MDASequence) -> Optional[TimingParams]:
        """Calculates and validates timing parameters from the MDASequence."""
        if not sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            return None

        try:
            z_axis_index = sequence.axis_order.index("z")
            num_z = sequence.shape[z_axis_index]
        except ValueError:
            num_z = 1

        num_t = sequence.shape[0]
        interval_s = self._get_time_interval_s(sequence.time_plan)
        scan_duration_s = (num_z * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        return TimingParams(
            num_z_slices=num_z,
            num_timepoints=num_t,
            repeat_delay_ms=repeat_delay_ms,
            total_images=num_z * num_t,
        )

    def _configure_hardware(
        self, sequence: MDASequence, params: TimingParams
    ) -> bool:
        """Configures all hardware components for the full MDA sequence."""
        z_plan = sequence.z_plan
        if not z_plan:
            return False

        if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
            logger.error("Failed to set camera to external trigger mode.")
            return False

        settings = AcquisitionSettings(
            num_slices=params.num_z_slices,
            step_size_um=self._get_z_step_size(z_plan),
            camera_exposure_ms=self._mmc.getExposure(),
        )
        configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

        z_positions = list(z_plan)
        galvo_amplitude_deg = 0.0
        if len(z_positions) > 1:
            z_range = max(z_positions) - min(z_positions)
            galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg

        configure_galvo_for_spim_scan(
            self._mmc,
            galvo_amplitude_deg,
            params.num_z_slices,
            num_repeats=params.num_timepoints,
            repeat_delay_ms=params.repeat_delay_ms,
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
        set_property(
            self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger"
        )
        set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
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
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        try:
            z_positions = list(z_plan)
            if len(z_positions) > 1:
                return abs(z_positions[1] - z_positions[0])
        except TypeError:
            pass
        return 0.0

    def _get_time_interval_s(self, time_plan: Optional[AnyTimePlan]) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0
