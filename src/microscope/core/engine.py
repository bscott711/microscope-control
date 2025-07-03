"""
engine.py

Custom MDA engine that integrates with ASI PLogic hardware for SPIM-style Z-stacks.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.metadata import frame_metadata
from useq import MDASequence

from .constants import HardwareConstants
from .hardware import (
    close_global_shutter,
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    open_global_shutter,
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
    """
    Custom MDA engine for PLogic-driven SPIM Z-stacks.

    This engine overrides the default run method to implement a custom hardware-timed
    acquisition sequence using an ASI PLogic card. It handles camera triggering,
    galvo scanning, and laser modulation. For sequences not involving a PLogic-defined
    axis, it falls back to the default MDAEngine implementation.
    """

    def __init__(self):
        # Fetch the CMMCorePlus singleton instance directly.
        # This removes the need to pass `mmc` when creating an engine instance.
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self.HW = HardwareConstants()

    def run(self, sequence: MDASequence):
        """
        Run an MDA sequence.

        Delegates to the custom PLogic Z-stack method if a 'p' axis is found,
        otherwise falls back to the default MDA engine.
        """
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack")
            # Note: Your custom method doesn't use after_fn, you may want to add it.
            self._run_custom_plogic_z_stack(sequence)
        else:
            logger.info("Falling back to default MDA engine")
            # The `run_mda` method returns a thread.
            # We are not blocking, so the acquisition will run in the background.
            self._mmc.run_mda(sequence)

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """
        Check if the PLogic engine should be used based on the Core Focus device.

        The custom engine is used only when the Core's Focus device is set
        to the specific Piezo stage, 'PiezoStage:P:34'.
        """
        try:
            # Get the label of the device currently assigned to the Core's Focus axis.
            current_focus_device = self._mmc.getProperty("Core", "Focus")

            # Check if the current focus device is the specific Piezo stage.
            result = current_focus_device == "PiezoStage:P:34"

            logger.debug(
                f"Checking Core Focus device. Current: '{current_focus_device}'. "
                f"Required: 'PiezoStage:P:34'. Should use PLogic engine? {result}"
            )
            return result

        except Exception as e:
            # It's safer to not use the custom engine if the state cannot be verified.
            logger.warning(f"Could not verify Core Focus device, falling back to default engine. Error: {e}")
            return False

    def _run_custom_plogic_z_stack(self, sequence: MDASequence):
        # Use the mmc instance stored during initialization.
        mmc = self._mmc
        logger.info("Starting custom PLogic Z-stack")

        # Get original autoshutter state before the try block.
        original_autoshutter = mmc.getAutoShutter()
        try:
            mmc.setAutoShutter(False)
            logger.debug("Auto-shutter disabled")

            # Setup camera trigger mode
            if not set_camera_trigger_mode_level_high(mmc, self.HW):
                raise RuntimeError("Failed to set camera to external trigger mode")

            # Open global shutter (BNC3 HIGH)
            open_global_shutter(mmc, self.HW)
            logger.debug("Global shutter opened (BNC3 HIGH)")

            # Configure PLogic for dual NRT pulses
            settings = AcquisitionSettings(
                num_slices=len(list(sequence)),
                step_size_um=1.0,  # You can derive this from z_plan
                laser_trig_duration_ms=10.0,
                camera_exposure_ms=mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(mmc, settings, self.HW)
            logger.debug("PLogic configured for dual NRT pulses")

            # Configure Galvo for SPIM scan
            galvo_amplitude_deg = 1.0  # Derived from step_size_um
            num_slices_ctrl = len(list(sequence))
            configure_galvo_for_spim_scan(mmc, galvo_amplitude_deg, num_slices_ctrl, self.HW)
            logger.debug("Galvo configured for SPIM scan")

            # Emit start signal
            meta = {
                "pixel_size": mmc.getPixelSizeUm(),
                "channels": [ch.config for ch in sequence.channels],
                "z_plan": str(sequence.z_plan),
            }
            # FIX: Use positional arguments for emit()
            mmc.mda.events.sequenceStarted.emit(sequence, meta)
            logger.debug("Emitted sequenceStarted signal")

            # Start camera acquisition
            mmc.startSequenceAcquisition(
                self.HW.camera_a_label,
                num_slices_ctrl,
                0,
                True,
            )
            logger.debug(f"Started camera sequence acquisition ({num_slices_ctrl} frames)")

            # Trigger hardware sequencing
            trigger_spim_scan_acquisition(mmc, self.HW.galvo_a_label)
            logger.debug("Triggered SPIM scan acquisition")

            # Wait for images
            images_collected = 0
            events = list(sequence)

            while images_collected < len(events):
                if mmc.getRemainingImageCount() > 0:
                    tagged_img = mmc.popNextTaggedImage()
                    event = events[images_collected]
                    meta = frame_metadata(mmc, mda_event=event)
                    # FIX: Use positional arguments for emit()
                    mmc.mda.events.frameReady.emit(tagged_img.pix, event, meta)
                    logger.debug(f"Frame collected: {event.index}")
                    images_collected += 1
                elif not mmc.isSequenceRunning():
                    raise RuntimeError("Sequence stopped unexpectedly.")
                else:
                    time.sleep(0.01)

        except Exception:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            mmc.stopSequenceAcquisition()
            reset_for_next_volume(mmc, self.HW.galvo_a_label)
            close_global_shutter(mmc, self.HW)
            # Correctly restore the original autoshutter state.
            mmc.setAutoShutter(original_autoshutter)
            # FIX: Use positional arguments for emit()
            mmc.mda.events.sequenceFinished.emit(sequence)
            logger.info("Custom PLogic Z-stack completed")
