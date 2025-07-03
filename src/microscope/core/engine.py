import logging
import time
from itertools import groupby

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
    reset_for_next_volume,
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

        num_z_slices = len(list(self.sequence.z_plan))

        try:
            # ----------------- ONE-TIME HARDWARE SETUP -----------------
            logger.info("Performing one-time hardware configuration...")
            self._mmc.setAutoShutter(False)

            if not set_camera_trigger_mode_level_high(self._mmc, self.HW):
                raise RuntimeError("Failed to set camera to external trigger mode")

            step_size = self._get_z_step_size(self.sequence.z_plan)
            settings = AcquisitionSettings(
                num_slices=num_z_slices,
                step_size_um=step_size,
                laser_trig_duration_ms=10.0,
                camera_exposure_ms=self._mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)
            logger.debug("PLogic configured.")

            galvo_amplitude_deg = 1.0  # Or derive from settings/sequence
            configure_galvo_for_spim_scan(self._mmc, galvo_amplitude_deg, num_z_slices, self.HW)
            logger.debug("Galvo configured.")
            logger.info("Hardware configuration complete.")
            # ---------------------------------------------------------

            # ---- MAIN ACQUISITION LOOP ----
            full_event_list = list(self.sequence)

            def key(e):
                return (e.index.get("t", 0), e.index.get("p", 0))

            interval_s = self._get_time_interval_s(self.sequence.time_plan)
            last_time_point_start = 0.0

            for (t_idx, p_idx), group in groupby(full_event_list, key=key):
                if not self._running:
                    break

                # -- Enforce Time Interval --
                if interval_s > 0 and t_idx > 0:
                    current_time = time.time()
                    wait_time = (last_time_point_start + interval_s) - current_time
                    if wait_time > 0:
                        logger.info(f"Waiting for {wait_time:.2f} seconds...")
                        time.sleep(wait_time)
                last_time_point_start = time.time()
                # -------------------------

                event_group = list(group)
                first_event = event_group[0]
                logger.info("Starting stack for T=%d, P=%d", t_idx, p_idx)

                if first_event.x_pos is not None and first_event.y_pos is not None:
                    logger.debug(
                        "Moving to XY: (%.2f, %.2f)",
                        first_event.x_pos,
                        first_event.y_pos,
                    )
                    self._mmc.setXYPosition(first_event.x_pos, first_event.y_pos)
                    self._mmc.waitForDevice(self._mmc.getXYStageDevice())

                # --- ACQUIRE ONE Z-STACK ---
                self._mmc.startSequenceAcquisition(self.HW.camera_a_label, num_z_slices, 0, True)
                trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label)

                for i in range(num_z_slices):
                    if not self._running:
                        break
                    while self._mmc.getRemainingImageCount() == 0:
                        if not self._mmc.isSequenceRunning():
                            raise RuntimeError("Camera sequence stopped unexpectedly.")
                        time.sleep(0.001)

                    tagged_img = self._mmc.popNextTaggedImage()
                    event = event_group[i]
                    meta = frame_metadata(self._mmc, mda_event=event)
                    self.frameReady.emit(tagged_img.pix, event, meta)
                    logger.debug(f"Frame collected: {event.index}")

                logger.info(f"Z-stack for T={t_idx}, P={p_idx} complete.")
                reset_for_next_volume(self._mmc, self.HW.galvo_a_label)

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
