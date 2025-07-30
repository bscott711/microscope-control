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
    Worker object for polling for images in a separate thread.
    """

    frameReady = Signal(object, object, object)
    acquisitionFinished = Signal(object)
    acquisitionError = Signal(str)

    def __init__(
        self,
        mmc: CMMCorePlus,
        sequence: MDASequence,
        total_images: int,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.total_images = total_images
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        """Polls for images from the camera sequence buffer."""
        try:
            if self.total_images == 0:
                logger.warning("Acquisition sequence has no images. Worker exiting.")
                return

            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for i in range(self.total_images):
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
                logger.info(f"Frame collected: {event.index}")

        except Exception as e:
            logger.error(f"Error in acquisition worker thread: {e}", exc_info=True)
            self.acquisitionError.emit(str(e))
        finally:
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Acquisition worker polling finished.")


class CustomPLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    events: MDASignaler

    def __init__(self):
        mmc = CMMCorePlus.instance()
        super().__init__(mmc)
        if not hasattr(self, "events"):
            self.events = MDASignaler()
        self.HW = HardwareConstants()
        self._worker: AcquisitionWorker | None = None
        self._thread: QThread | None = None
        self._original_autoshutter: bool | None = None

    def run(self, sequence: MDASequence):
        if self._should_use_plogic(sequence):
            self._run_plogic_acquisition(sequence)
        else:
            super().run(sequence)  # type: ignore

    def setup_hardware(self, sequence: MDASequence, total_images: int):
        """Configure all hardware for the PLogic acquisition. Runs in main thread."""
        logger.info("Configuring hardware from main thread...")
        self._original_autoshutter = self._mmc.getAutoShutter()
        self._mmc.setAutoShutter(False)

        if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
            raise RuntimeError("Failed to set camera to external trigger mode")

        z_plan = sequence.z_plan
        if not z_plan:
            raise ValueError("PLogic acquisition requires a z_plan.")

        num_z_slices = len(list(z_plan))
        step_size = self._get_z_step_size(z_plan)
        exposure_ms = self._mmc.getExposure()
        scan_duration_ms = num_z_slices * exposure_ms
        time_interval_s = self._get_time_interval_s(sequence.time_plan)
        repeat_delay_ms = max(0, (time_interval_s * 1000) - scan_duration_ms)

        settings = AcquisitionSettings(
            num_slices=num_z_slices,
            step_size_um=step_size,
            camera_exposure_ms=exposure_ms,
        )
        configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

        z_positions = list(z_plan)
        z_range = max(z_positions) - min(z_positions) if len(z_positions) > 1 else 0
        galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg
        num_timepoints = int(total_images / num_z_slices) if num_z_slices > 0 else 0

        configure_galvo_for_spim_scan(
            self._mmc,
            galvo_amplitude_deg,
            num_slices=num_z_slices,
            num_repeats=num_timepoints,
            repeat_delay_ms=repeat_delay_ms,
            hw=self.HW,
        )

    def cleanup_hardware(self):
        """Reset all hardware post-acquisition. Runs in main thread."""
        logger.info("Cleaning up hardware from main thread...")
        set_property(self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger")
        set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
        if self._mmc.isSequenceRunning():
            self._mmc.stopSequenceAcquisition()
        if self._original_autoshutter is not None:
            self._mmc.setAutoShutter(self._original_autoshutter)

    def _run_plogic_acquisition(self, sequence: MDASequence):
        """Sets up hardware, runs worker, and cleans up, all in a blocking fashion."""
        total_images = sum(1 for _ in sequence)
        try:
            self.setup_hardware(sequence, total_images)

            self._worker = AcquisitionWorker(self._mmc, sequence, total_images)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            self._worker.frameReady.connect(self._on_frame_ready)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)
            self._thread.started.connect(self._worker.run)

            self._mmc.startSequenceAcquisition(total_images, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label)

            loop = QEventLoop()
            self.events.sequenceFinished.connect(lambda: loop.quit())
            self.events.sequenceStarted.emit(sequence)

            self._thread.start()
            loop.exec_()

        except Exception as e:
            logger.error(f"Error during PLogic acquisition setup: {e}", exc_info=True)
            self.events.sequenceFinished.emit(sequence)
        finally:
            self.cleanup_hardware()

    def _on_frame_ready(self, frame, event, meta):
        self.events.frameReady.emit(frame, event, meta)

    def _on_acquisition_finished(self, sequence):
        """This slot now only cleans up the thread and emits the final event."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self.events.sequenceFinished.emit(sequence)
        logger.info("Custom PLogic MDAEngine finished.")

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            return current_focus_device == self.HW.piezo_a_label
        except Exception as e:
            logger.warning(f"Could not verify Core Focus device: {e}")
            return False

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
