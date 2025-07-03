import logging
import time
from itertools import groupby

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.metadata import frame_metadata
from useq import MDASequence, ZAboveBelow, ZRangeAround

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


class CustomPLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self):
        """Initialize the engine and fetch the CMMCorePlus instance."""
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self.HW = HardwareConstants()

    def run(self, sequence: MDASequence):
        """Run an MDA sequence, delegating to the correct method."""
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._run_hardware_timed_sequence(sequence)
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

    def _get_z_step_size(self, z_plan) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        # For ZAbsolutePositions or other types, calculate from the first two points
        if z_plan and len(z_plan) > 1:
            positions = list(z_plan)
            return abs(positions[1] - positions[0])
        return 0.0

    def _run_hardware_timed_sequence(self, sequence: MDASequence):
        """
        Execute a hardware-timed MDA sequence.

        Performs a one-time hardware configuration, then loops through
        timepoints and positions, triggering a Z-stack at each one.
        """
        mmc = self._mmc
        original_autoshutter = mmc.getAutoShutter()

        if not sequence.z_plan:
            raise ValueError("PLogic acquisition requires a Z-plan.")
        num_z_slices = len(list(sequence.z_plan))

        try:
            # ----------------- ONE-TIME HARDWARE SETUP -----------------
            logger.info("Performing one-time hardware configuration...")
            mmc.setAutoShutter(False)

            if not set_camera_trigger_mode_level_high(mmc, self.HW):
                raise RuntimeError("Failed to set camera to external trigger mode")

            step_size = self._get_z_step_size(sequence.z_plan)
            settings = AcquisitionSettings(
                num_slices=num_z_slices,
                step_size_um=step_size,
                laser_trig_duration_ms=10.0,
                camera_exposure_ms=mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(mmc, settings, self.HW)
            logger.debug("PLogic configured for dual NRT pulses.")

            galvo_amplitude_deg = 1.0  # Or derive from settings/sequence
            configure_galvo_for_spim_scan(mmc, galvo_amplitude_deg, num_z_slices, self.HW)
            logger.debug("Galvo configured for SPIM scan.")
            logger.info("Hardware configuration complete.")
            # ---------------------------------------------------------

            mmc.mda.events.sequenceStarted.emit(sequence, {})

            # ---- LOOP THROUGH TIMEPOINTS AND POSITIONS ----
            full_event_list = list(sequence)

            # FIX: Use a lambda function to get the t and p indices from event.index
            def key(e):
                return (e.index.get("t", 0), e.index.get("p", 0))

            for (t_idx, p_idx), group in groupby(full_event_list, key=key):
                event_group = list(group)
                first_event = event_group[0]
                logger.info("Starting stack for T=%d, P=%d", t_idx, p_idx)

                # Move to the XY position for the current stack
                if first_event.x_pos is not None and first_event.y_pos is not None:
                    logger.debug(
                        "Moving to XY: (%.2f, %.2f)",
                        first_event.x_pos,
                        first_event.y_pos,
                    )
                    mmc.setXYPosition(first_event.x_pos, first_event.y_pos)
                    mmc.waitForDevice(mmc.getXYStageDevice())

                # --- ACQUIRE ONE Z-STACK ---
                mmc.startSequenceAcquisition(self.HW.camera_a_label, num_z_slices, 0, True)
                trigger_spim_scan_acquisition(mmc, self.HW.galvo_a_label)

                for i in range(num_z_slices):
                    while mmc.getRemainingImageCount() == 0:
                        if not mmc.isSequenceRunning():
                            raise RuntimeError("Camera sequence stopped unexpectedly.")
                        time.sleep(0.001)

                    tagged_img = mmc.popNextTaggedImage()
                    event = event_group[i]
                    meta = frame_metadata(mmc, mda_event=event)
                    mmc.mda.events.frameReady.emit(tagged_img.pix, event, meta)
                    logger.debug("Frame collected: %s", event.index)

                logger.info("Z-stack for T=%d, P=%d complete.", t_idx, p_idx)
                reset_for_next_volume(mmc, self.HW.galvo_a_label)

        except Exception:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            mmc.stopSequenceAcquisition()
            mmc.setAutoShutter(original_autoshutter)
            mmc.mda.events.sequenceFinished.emit(sequence)
            logger.info("Custom PLogic Z-stack completed.")
