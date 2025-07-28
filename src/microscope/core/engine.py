import logging
import time

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, QThread, Signal  # type: ignore
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
    set_camera_trigger_mode_level_high,
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

    Signals:
        frameReady (object, object, object): Emitted when a new frame is ready.
                                              Provides (image, event, metadata).
        acquisitionFinished (object): Emitted when the acquisition is finished.
                                      Provides the sequence object.
    """

    frameReady = Signal(object, object, object)
    acquisitionFinished = Signal(object)

    def __init__(self, mmc: CMMCorePlus, sequence: MDASequence, parent=None):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.HW = HardwareConstants()
        self._running = True

    def stop(self):
        """Stop the acquisition."""
        self._running = False

    def run(self):
        """Execute a hardware-timed MDA sequence."""
        original_autoshutter = self._mmc.getAutoShutter()

        if not self.sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            return

        # --- Get sequence parameters ---
        num_z_slices = len(list(self.sequence.z_plan))
        num_timepoints = self.sequence.time_plan.loops if self.sequence.time_plan else 1
        interval_s = self._get_time_interval_s(self.sequence.time_plan)
        # The controller delay is from the end of one scan to the start of the next.
        # We must subtract the time it takes to acquire one z-stack.
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
            if not set_camera_trigger_mode_level_high(self._mmc, self.HW):
                raise RuntimeError("Failed to set camera to external trigger mode")

            step_size = self._get_z_step_size(self.sequence.z_plan)
            settings = AcquisitionSettings(
                num_slices=num_z_slices,
                step_size_um=step_size,
                camera_exposure_ms=self._mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

            galvo_amplitude_deg = 1.0  # Or derive from settings/sequence
            configure_galvo_for_spim_scan(
                self._mmc,
                galvo_amplitude_deg,
                num_z_slices,
                num_repeats=num_timepoints,
                repeat_delay_ms=repeat_delay_ms,
                hw=self.HW,
            )
            logger.info("Hardware configured for full time-series.")
            # ---------------------------------------------------------

            # ---- SINGLE TRIGGER AND COLLECTION LOOP ----
            self._mmc.startSequenceAcquisition(self.HW.camera_a_label, total_images_expected, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label)

            # Create an iterator to emit the correct event with each image
            events = iter(self.sequence)

            for i in range(total_images_expected):
                if not self._running:
                    break
                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning():
                        raise RuntimeError("Camera sequence stopped unexpectedly.")
                    time.sleep(0.001)

                tagged_img = self._mmc.popNextTaggedImage()
                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug(f"Frame collected: {event.index}")

            logger.info("Hardware-driven time-series complete.")

        except Exception:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            self._mmc.stopSequenceAcquisition()
            self._mmc.setAutoShutter(original_autoshutter)
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Custom PLogic Z-stack completed.")

    def _get_z_step_size(self, z_plan) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        if z_plan and len(z_plan) > 1:
            positions = list(z_plan)
            return abs(positions[1] - positions[0])
        return 0.0

    def _get_time_interval_s(self, time_plan) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0


class CustomPLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self):
        """Initialize the engine and fetch the CMMCorePlus instance."""
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self.HW = HardwareConstants()
        self._worker = None
        self._thread = None

    def run(self, sequence: MDASequence):
        """Run an MDA sequence, delegating to the correct method."""
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})
            self._worker = AcquisitionWorker(self._mmc, sequence)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            # Connect signals
            self._worker.frameReady.connect(self._on_frame_ready)
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
            result = current_focus_device == "PiezoStage:P:34"
            logger.debug(
                f"Checking Core Focus. Current: '{current_focus_device}'. "
                f"Required: 'PiezoStage:P:34'. Should use PLogic? {result}"
            )
            return result
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _on_frame_ready(self, frame, event, meta):
        """Slot to handle the frameReady signal from the worker."""
        self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def _on_acquisition_finished(self, sequence):
        """Slot to handle the acquisitionFinished signal from the worker."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._mmc.mda.events.sequenceFinished.emit(sequence)
        self._mmc.mda.events.sequenceFinished.emit(sequence)
