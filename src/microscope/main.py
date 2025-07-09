# src/microscope/main.py

import logging
import sys

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_gui._qt.QtAds import CDockWidget, DockWidgetArea
from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication
from useq import MDASequence

from microscope.core import widgets

# Import the custom actions instead of defining them locally
from microscope.core.actions import custom_snap_image, custom_toggle_live
from microscope.core.constants import HardwareConstants
from microscope.core.engine import CustomPLogicMDAEngine
from microscope.core.hardware import (
    close_global_shutter,
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


def main():
    """Launch the GUI, set up the engine, and manage hardware states."""
    # --- Override Default Actions ---
    # We replace the default triggered functions with our own implementations
    # from the core.actions module.
    core_actions.snap_action.on_triggered = custom_snap_image
    core_actions.toggle_live_action.on_triggered = custom_toggle_live
    logger.info("Default snap and live actions have been replaced with custom versions.")

    mmc = CMMCorePlus.instance()
    hw = HardwareConstants()

    # --- Application Setup ---
    window = create_mmgui(exec_app=False)

    # --- ADD THE CUSTOM GALVO WIDGET TO THE MAIN WINDOW ---
    galvo_widget = widgets.GalvoControlWidget(mmc=mmc, device_label=hw.galvo_a_label)
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
    open_global_shutter(mmc, hw)

    logger.info("Setting camera trigger modes on startup...")
    set_camera_trigger_mode_level_high(mmc, hw)

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
        mmc.setProperty(hw.galvo_a_label, "BeamEnabled", "No")
        logger.info("Closing global shutter.")
        close_global_shutter(mmc, hw)
        logger.info("Application cleanup complete.")

    app.aboutToQuit.connect(on_exit)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
