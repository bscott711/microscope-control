# src/microscope/controller/application_controller.py
"""
Main application controller for the microscope.
Now a thin orchestrator that wires components together.
"""

import logging
from functools import wraps
from typing import Callable, Optional

from pymmcore_gui import WidgetAction
from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus

from microscope.application import setup_mda_widget
from microscope.model.hardware_model import HardwareConstants
from microscope.view.main_view import MainView

logger = logging.getLogger(__name__)


class ApplicationController:
    """
    The main controller for the microscope application.
    Orchestrates the View, Model, and Acquisition Engine.
    """

    def __init__(self):
        self.mmc = CMMCorePlus.instance()
        self.model = HardwareConstants()
        self.view = MainView()
        self._original_snap_func: Optional[Callable] = None
        self._original_live_func: Optional[Callable] = None
        self._setup_logic()

    def run(self):
        """Starts the application."""
        self.view.show()

    def _setup_logic(self):
        """Wire up all the application logic."""
        self._disconnect_faulty_snap_handler()
        self._wrap_snap_action()
        self._wrap_toggle_live_action()

        # Hardware setup using the public hardware API
        from microscope.hardware import open_global_shutter, set_camera_trigger_mode_level_high

        open_global_shutter(self.mmc, self.model)
        set_camera_trigger_mode_level_high(self.mmc, self.model)

        # MDA setup using the new service
        mda_widget = self.view.get_widget(WidgetAction.MDA_WIDGET)
        if mda_widget:
            setup_mda_widget(mda_widget, self.mmc, self.model)
        else:
            logger.warning("Could not find MDA widget to intercept.")

        # Connect app cleanup
        if app := self.view.app():
            app.aboutToQuit.connect(self._on_exit)

    def _disconnect_faulty_snap_handler(self):
        """Disconnect the default snap handler to prevent race condition."""
        try:
            manager = self.view.window._viewers_manager
            preview_widget = manager._create_or_show_img_preview()
            if preview_widget:
                self.mmc.events.imageSnapped.disconnect(preview_widget.append)
            logger.info("Successfully disconnected faulty preview snap handler.")
        except Exception as e:
            logger.error("Failed to disconnect faulty snap handler: %s", e)

    def _wrap_snap_action(self):
        """Wrap snap action to control laser and beam."""
        from microscope.hardware import disable_live_laser, enable_live_laser

        self._original_snap_func = core_actions.snap_action.on_triggered
        if self._original_snap_func:

            def snap_cleanup():
                disable_live_laser(self.mmc, self.model)
                self.mmc.events.imageSnapped.disconnect(snap_cleanup)
                logger.info("Laser and beam disabled. Snap cleanup complete.")

            @wraps(self._original_snap_func)
            def snap_with_laser(*args, **kwargs):
                logger.info("Snap action triggered.")
                self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
                enable_live_laser(self.mmc, self.model)
                self.mmc.events.imageSnapped.connect(snap_cleanup)
                self._original_snap_func(*args, **kwargs)  # type: ignore

            core_actions.snap_action.on_triggered = snap_with_laser
            logger.info("Snap action wired for hardware control.")

    def _wrap_toggle_live_action(self):
        """Wrap toggle live action to control laser and beam."""
        from microscope.hardware import disable_live_laser, enable_live_laser

        self._original_live_func = core_actions.toggle_live_action.on_triggered
        if self._original_live_func:

            @wraps(self._original_live_func)
            def toggle_live_with_laser(*args, **kwargs):
                if self.mmc.isSequenceRunning():
                    self._original_live_func(*args, **kwargs)  # type: ignore
                    disable_live_laser(self.mmc, self.model)
                    logger.info("Live mode, laser disabled.")
                else:
                    self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
                    enable_live_laser(self.mmc, self.model)
                    self._original_live_func(*args, **kwargs)  # type: ignore
                    logger.info("Live mode and laser enabled.")

            core_actions.toggle_live_action.on_triggered = toggle_live_with_laser
            logger.info("Live action wired for hardware control.")

    def _on_exit(self):
        """Clean up hardware state on exit."""
        from microscope.hardware import close_global_shutter

        logger.info("Application closing. Cleaning up hardware.")
        self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        if self._original_snap_func:
            core_actions.snap_action.on_triggered = self._original_snap_func
        if self._original_live_func:
            core_actions.toggle_live_action.on_triggered = self._original_live_func
        logger.info("Original snap/live actions restored. Cleanup complete.")
