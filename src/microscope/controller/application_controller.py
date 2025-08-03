# src/microscope/controller/application_controller.py
"""
Main application controller for the microscope.
A thin orchestrator that wires components together.
"""

import logging

from pymmcore_gui import WidgetAction
from pymmcore_plus import CMMCorePlus

from microscope.application import setup_mda_widget
from microscope.hardware import close_global_shutter, initialize_system_hardware
from microscope.model.hardware_model import HardwareConstants
from microscope.view.main_view import MainView

from .action_interceptor import ActionInterceptor

logger = logging.getLogger(__name__)


class ApplicationController:
    """
    The main controller for the microscope application.

    Orchestrates the View, Model, and services like the ActionInterceptor
    and HardwareInitializer.
    """

    def __init__(self, hw_constants: HardwareConstants):
        self.mmc = CMMCorePlus.instance()
        self.model = hw_constants
        self.view = MainView()
        self.interceptor = ActionInterceptor(self.mmc, self.model)
        self._setup_logic()

    def run(self) -> None:
        """Starts the application by showing the main view."""
        self.view.show()

    def _setup_logic(self) -> None:
        """Wire up all the application logic."""
        self._disconnect_faulty_snap_handler()

        # Use the dedicated interceptor to wrap actions
        self.interceptor.wrap_snap_action()
        self.interceptor.wrap_toggle_live_action()

        # Use the dedicated hardware initializer
        initialize_system_hardware(self.mmc, self.model)

        # Use the dedicated MDA setup service
        mda_widget = self.view.get_widget(WidgetAction.MDA_WIDGET)
        if mda_widget:
            setup_mda_widget(mda_widget, self.mmc, self.model)
        else:
            logger.warning("Could not find MDA widget to intercept.")

        # Connect app cleanup
        if app := self.view.app():
            app.aboutToQuit.connect(self._on_exit)

    def _disconnect_faulty_snap_handler(self) -> None:
        """Disconnect the default snap handler to prevent race condition."""
        try:
            manager = self.view.window._viewers_manager
            preview_widget = manager._create_or_show_img_preview()
            if preview_widget:
                self.mmc.events.imageSnapped.disconnect(preview_widget.append)
            logger.info("Successfully disconnected faulty preview snap handler.")
        except Exception as e:
            logger.error("Failed to disconnect faulty snap handler: %s", e)

    def _on_exit(self) -> None:
        """Clean up hardware state and restore actions on exit."""
        logger.info("Application closing. Cleaning up hardware.")
        self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        self.interceptor.restore_actions()
        logger.info("Cleanup complete.")
