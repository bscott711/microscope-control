# src/microscope/controller/main.py

import logging

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_plus import CMMCorePlus

from microscope.core import (
    CustomPLogicMDAEngine,
    HardwareConstants,
    close_global_shutter,
    open_global_shutter,
    set_camera_trigger_mode_level_high,
)

from .actions import ActionsController
from .mda import MDAController

logger = logging.getLogger(__name__)


class ApplicationController:
    """
    The main orchestrator for the microscope application.
    """

    def __init__(self, app):
        self.app = app
        self.mmc = CMMCorePlus.instance()
        self.hw = HardwareConstants()

        self._setup_hardware()
        self.window = create_mmgui(exec_app=False)

        # Instantiate sub-controllers
        self.actions_controller = ActionsController(self)
        self.mda_controller = MDAController(self)

        self._connect_signals()

    def _setup_hardware(self):
        """Initializes hardware states at application startup."""
        open_global_shutter(self.mmc, self.hw)
        set_camera_trigger_mode_level_high(self.mmc, self.hw)
        engine = CustomPLogicMDAEngine()
        self.mmc.register_mda_engine(engine)
        logger.info("Custom PLogic MDA Engine registered.")

    def _connect_signals(self):
        """Connects UI signals to controller slots."""
        self.actions_controller.connect_signals()

        mda_widget = self.window.get_widget(WidgetAction.MDA_WIDGET)
        if mda_widget:
            mda_widget.execute_mda = self.mda_controller.run_mda # type: ignore
            logger.info("MDA 'Run' button has been wired to the MDA controller.")
        else:
            logger.warning("Could not find MDA widget to intercept.")

        self.app.aboutToQuit.connect(self._on_exit)

    def show_window(self):
        """Shows the main application window."""
        self.window.show()

    def _on_exit(self):
        """Clean up hardware state when the application quits."""
        self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.hw)
        self.actions_controller.cleanup()
        logger.info("Application cleanup complete.")
