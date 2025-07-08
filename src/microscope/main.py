# src/microscope/main.py

import logging
import sys

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_gui._qt.QtAds import CDockWidget, DockWidgetArea
from pymmcore_gui.actions import QCoreAction, core_actions
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication
from useq import MDASequence

from microscope.core import widgets
from microscope.core.constants import HardwareConstants
from microscope.core.engine import CustomPLogicMDAEngine
from microscope.core.hardware import (
    close_global_shutter,
    disable_live_laser,
    enable_live_laser,
    open_global_shutter,
    set_camera_trigger_mode_level_high,
)

# Set up logger
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


# --- Custom Action Implementations ---
# These functions contain all the logic for your custom hardware control
# combined with the basic snap/live functionality.


def custom_snap_image(action: QCoreAction, checked: bool) -> None:
    """
    Snap an image with laser and beam control.
    This function replaces the default snap action. It enables the beam and
    laser, triggers a snap, and then disables them using a one-shot callback
    connected to the imageSnapped event.
    """
    mmc = action.mmc
    HW = HardwareConstants()
    logger.info("Custom snap action triggered.")

    def snap_cleanup():
        """A one-shot callback to turn off the laser and beam after snap."""
        logger.debug("snap_cleanup: Disabling PLogic laser output.")
        disable_live_laser(mmc, HW)
        #logger.debug("Disabling SPIM beam after snap.")
        #mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
        logger.debug("snap_cleanup: Disconnecting one-shot signal.")
        try:
            mmc.events.imageSnapped.disconnect(snap_cleanup)
        except (KeyError, ValueError):
            logger.warning("Could not disconnect snap_cleanup signal.")
        logger.info("Laser and beam disabled. Snap cleanup complete.")

    if mmc.isSequenceRunning():
        mmc.stopSequenceAcquisition()

    logger.debug("Enabling SPIM beam for snap...")
    mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
    logger.debug("Enabling PLogic laser output for snap...")
    enable_live_laser(mmc, HW)

    logger.debug("Connecting snap_cleanup to imageSnapped signal.")
    mmc.events.imageSnapped.connect(snap_cleanup)

    logger.debug("Calling mmc.snapImage()...")
    try:
        mmc.snapImage()
    except Exception as e:
        logger.error(f"Error during snapImage, forcing cleanup: {e}")
        # If snap fails, the imageSnapped event may not fire,
        # so we call cleanup manually.
        snap_cleanup()


def custom_toggle_live(action: QCoreAction, checked: bool) -> None:
    """
    Start or stop live mode with laser and beam control.
    This function replaces the default toggle-live action.
    If starting live mode, it enables the beam and laser first.
    If stopping live mode, it disables them afterward.
    """
    mmc = action.mmc
    HW = HardwareConstants()
    logger.info("Custom toggle live action triggered.")

    if mmc.isSequenceRunning():
        logger.debug("Live mode is ON. Stopping...")
        mmc.stopSequenceAcquisition()
        logger.debug("Disabling PLogic laser output after live mode...")
        disable_live_laser(mmc, HW)
        #logger.debug("Disabling SPIM beam after live mode...")
        #mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
        logger.info("Live mode, laser, and beam disabled.")
    else:
        logger.debug("Live mode is OFF. Starting...")
        # Enable the hardware before starting the sequence
        logger.debug("Enabling SPIM beam for live mode...")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
        logger.debug("Enabling PLogic laser output for live mode...")
        enable_live_laser(mmc, HW)

        logger.debug("Starting continuous sequence acquisition...")
        mmc.startContinuousSequenceAcquisition(0)

        # Re-assert the state AFTER starting the sequence. This handles cases
        # where starting the acquisition resets device properties.
        logger.debug("Re-asserting beam and laser state after starting sequence.")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
        enable_live_laser(mmc, HW)

        logger.info("Live mode, laser, and beam enabled.")


def main():
    """Launch the GUI, set up the engine, and manage hardware states."""
    # --- Override Default Actions ---
    # We replace the default triggered functions with our own implementations
    # at the very beginning of the application.
    core_actions.snap_action.on_triggered = custom_snap_image
    core_actions.toggle_live_action.on_triggered = custom_toggle_live
    logger.info("Default snap and live actions have been replaced with custom versions.")

    mmc = CMMCorePlus.instance()
    HW = HardwareConstants()

    # --- Application Setup ---
    window = create_mmgui(exec_app=False)

    # --- ADD THE CUSTOM GALVO WIDGET TO THE MAIN WINDOW ---
    galvo_widget = widgets.GalvoControlWidget(mmc=mmc, device_label=HW.galvo_a_label)
    dock_widget = CDockWidget(window.dock_manager, "Galvo A Control")
    dock_widget.setWidget(galvo_widget)  # type: ignore
    window.dock_manager.addDockWidget(DockWidgetArea.RightDockWidgetArea, dock_widget)
    logger.info("Custom Galvo Control widget added to the main window.")
    # ----------------------------------------------------

    app = QApplication.instance()
    if not app:
        logger.fatal("Could not get QApplication instance.")
        return

    logger.info("Opening global shutter on startup...")
    open_global_shutter(mmc, HW)

    logger.info("Setting camera trigger modes on startup...")
    set_camera_trigger_mode_level_high(mmc, HW)

    engine = CustomPLogicMDAEngine()
    mmc.register_mda_engine(engine)
    logger.info("Custom PLogic MDA Engine registered.")

    mda_widget = window.get_widget(WidgetAction.MDA_WIDGET)
    if mda_widget:

        def mda_runner(output=None):
            """Wrapper to call our engine from the GUI."""
            sequence: MDASequence = mda_widget.value()
            engine.run(sequence)

        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        logger.warning("Could not find MDA widget to intercept.")

    def on_exit():
        """Clean up hardware state when the application quits."""
        logger.info("Application closing. Ensuring SPIM beam is disabled.")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
        logger.info("Closing global shutter.")
        close_global_shutter(mmc, HW)
        logger.info("Application cleanup complete.")

    app.aboutToQuit.connect(on_exit)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
