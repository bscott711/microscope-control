# src/microscope/core/engine.py

import logging
import time
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.mda.events import MDASignaler
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QEventLoop, QObject, QThread, Signal  # type: ignore
from useq import (
    MDASequence,
    MultiPhaseTimePlan,
    TIntervalLoops,
    ZAboveBelow,
    ZRangeAround,
)

from .constants import HardwareConstants
from .hardware import (
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
    trigger_spim_scan_acquisition,
)
from .settings import AcquisitionSettings

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.propagate = False


class AcquisitionWorker(QObject):
    """
    Worker object for running hardware-timed acquisitions in a separate thread.
    It emits signals that the engine can then relay to the main event bus.
    """

    frameReady = Signal(object, object, object)  # image, event, metadata
    acquisitionFinished = Signal(object)  # sequence

    def __init__(
        self,
        mmc: CMMCorePlus,
        sequence: MDASequence,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.HW = HardwareConstants()
        self._running = True

    def stop(self):
        """Stop the acquisition."""
        self._running = False
        logger.info("Acquisition stop requested.")

    def run(self):
        """Execute a hardware-timed MDA sequence."""
        original_autoshutter = self._mmc.getAutoShutter()

        if not self.sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            return

        # --- Get sequence parameters ---
        num_z_slices = len(list(self.sequence.z_plan))
        num_timepoints = self.sequence.shape[0]
        interval_s = self._get_time_interval_s(self.sequence.time_plan)
        scan_duration_s = (num_z_slices * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        total_images_expected = num_z_slices * num_timepoints
        logger.info(
            "Starting hardware-timed series: %d timepoints, %d z-slices, %.2f ms interval",
            num_timepoints,
            num_z_slices,
            repeat_delay_ms,
        )

        try:
            # ----------------- ONE-TIME HARDWARE SETUP -----------------
            self._mmc.setAutoShutter(False)
            if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
                raise RuntimeError("Failed to set camera to external trigger mode")

            step_size = self._get_z_step_size(self.sequence.z_plan)
            settings = AcquisitionSettings(
                num_slices=num_z_slices,
                step_size_um=step_size,
                camera_exposure_ms=self._mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

            z_positions = list(self.sequence.z_plan)
            if len(z_positions) > 1:
                z_range = max(z_positions) - min(z_positions)
                galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg
            else:
                galvo_amplitude_deg = 0

            configure_galvo_for_spim_scan(
                self._mmc,
                galvo_amplitude_deg,
                num_z_slices,
                num_repeats=num_timepoints,
                repeat_delay_ms=repeat_delay_ms,
                hw=self.HW,
            )
            # ---------------------------------------------------------

            # ---- SINGLE TRIGGER AND COLLECTION LOOP ----
            self._mmc.startSequenceAcquisition(self.HW.camera_a_label, total_images_expected, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label)

            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for i in range(total_images_expected):
                if not self._running:
                    break
                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning() and self._running:
                        raise RuntimeError("Camera sequence stopped unexpectedly.")
                    time.sleep(0.001)

                tagged_img = self._mmc.popNextTaggedImage()
                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug(f"Frame collected: {event.index}")

        except Exception as _e:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            set_property(self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger")
            set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
            self._mmc.stopSequenceAcquisition()
            self._mmc.setAutoShutter(original_autoshutter)
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Custom PLogic acquisition worker finished.")

    def _get_z_step_size(self, z_plan) -> float:
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        if z_plan and len(z_plan) > 1:
            positions = list(z_plan)
            return abs(positions[1] - positions[0])
        return 0.0

    def _get_time_interval_s(self, time_plan) -> float:
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0


class CustomPLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    events: MDASignaler

    def __init__(self):
        """
        Initialize the engine.
        This calls the parent constructor and then defensively ensures
        that the `events` attribute has been created.
        """
        mmc = CMMCorePlus.instance()
        super().__init__(mmc)

        if not hasattr(self, "events"):
            self.events = MDASignaler()

        self.HW = HardwareConstants()
        self._worker: AcquisitionWorker | None = None
        self._thread: QThread | None = None

    def run(self, sequence: MDASequence):
        """
        Run an MDA sequence.
        If the sequence is suited for PLogic, it runs the hardware-timed routine.
        Otherwise, it falls back to the default software-timed engine.
        """
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._run_plogic_acquisition(sequence)
        else:
            logger.info("Falling back to default MDA engine")
            super().run(sequence)  # type: ignore

    def _run_plogic_acquisition(self, sequence: MDASequence):
        """Sets up and starts the AcquisitionWorker in a blocking fashion."""
        self._worker = AcquisitionWorker(self._mmc, sequence)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._worker.frameReady.connect(self._on_frame_ready)
        self._worker.acquisitionFinished.connect(self._on_acquisition_finished)
        self._thread.started.connect(self._worker.run)

        loop = QEventLoop()
        self.events.sequenceFinished.connect(lambda: loop.quit())

        try:
            self.events.sequenceStarted.emit(sequence)
            self._thread.start()
            loop.exec_()
        finally:
            self.events.sequenceFinished.disconnect(loop.quit)

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            return current_focus_device == self.HW.piezo_a_label
        except Exception as e:
            logger.warning(f"Could not verify Core Focus device: {e}")
            return False

    def _on_frame_ready(self, frame, event, meta):
        """Slot to receive frame from worker and emit on the engine's event bus."""
        self.events.frameReady.emit(frame, event, meta)

    def _on_acquisition_finished(self, sequence):
        """Slot to clean up and emit the sequenceFinished event."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.events.sequenceFinished.emit(sequence)
        logger.info("Custom PLogic MDAEngine finished.")
