# src/microscope/core/actions.py

import logging

from pymmcore_gui.actions import QCoreAction
from pymmcore_plus import CMMCorePlus

from .constants import HardwareConstants
from .hardware import disable_live_laser, enable_live_laser

logger = logging.getLogger(__name__)


def prepare_for_acquisition(mmc: CMMCorePlus, hw: HardwareConstants) -> None:
    """Enable the beam and laser in preparation for an acquisition."""
    logger.debug("Enabling SPIM beam...")
    mmc.setProperty(hw.galvo_a_label, "BeamEnabled", "Yes")
    logger.debug("Enabling PLogic laser output...")
    enable_live_laser(mmc, hw)


def cleanup_after_acquisition(mmc: CMMCorePlus, hw: HardwareConstants) -> None:
    """Disable the laser after an acquisition."""
    logger.debug("Disabling PLogic laser output.")
    disable_live_laser(mmc, hw)


def custom_snap_image(action: QCoreAction, checked: bool) -> None:
    """Snap an image with laser and beam control using helper functions."""
    mmc: CMMCorePlus = action.mmc
    hw = HardwareConstants()
    logger.debug("Custom snap action triggered.")

    def snap_cleanup():
        """A one-shot callback to clean up after snap."""
        cleanup_after_acquisition(mmc, hw)
        logger.debug("snap_cleanup: Disconnecting one-shot signal.")
        try:
            mmc.events.imageSnapped.disconnect(snap_cleanup)
        except (KeyError, ValueError):
            logger.warning("Could not disconnect snap_cleanup signal.")
        logger.debug("Snap cleanup complete.")

    if mmc.isSequenceRunning():
        mmc.stopSequenceAcquisition()

    prepare_for_acquisition(mmc, hw)

    logger.debug("Connecting snap_cleanup to imageSnapped signal.")
    mmc.events.imageSnapped.connect(snap_cleanup)

    logger.debug("Calling mmc.snapImage()...")
    try:
        mmc.snapImage()
    except Exception as e:
        logger.error(f"Error during snapImage, forcing cleanup: {e}")
        snap_cleanup()


def custom_toggle_live(action: QCoreAction, checked: bool) -> None:
    """Start or stop live mode with laser and beam control using helper functions."""
    mmc: CMMCorePlus = action.mmc
    hw = HardwareConstants()
    logger.debug("Custom toggle live action triggered.")

    if mmc.isSequenceRunning():
        logger.debug("Live mode is ON. Stopping...")
        mmc.stopSequenceAcquisition()
        cleanup_after_acquisition(mmc, hw)
        logger.debug("Live mode and laser disabled.")
    else:
        logger.debug("Live mode is OFF. Starting...")
        prepare_for_acquisition(mmc, hw)
        mmc.startContinuousSequenceAcquisition(0)
        # Re-assert the state AFTER starting the sequence.
        logger.debug("Re-asserting beam and laser state after starting sequence.")
        prepare_for_acquisition(mmc, hw)
        logger.debug("Live mode started.")
