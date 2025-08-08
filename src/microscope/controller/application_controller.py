# src/microscope/controller/application_controller.py
"""
Main application controller for the microscope.
"""

import functools
import logging
from typing import Any

from pymmcore_plus import CMMCorePlus

from microscope.acquisition import PLogicMDAEngine
from microscope.application import setup_mda_widget
from microscope.hardware import (
    close_global_shutter,
    initialize_system_hardware,
    set_property,
)
from microscope.model.hardware_model import HardwareConstants
from microscope.view.main_view import MainView

from .action_interceptor import ActionInterceptor

logger = logging.getLogger(__name__)


class ApplicationController:
    """
    The main controller for the microscope application.
    """

    def __init__(self, hw_constants: HardwareConstants):
        self.mmc = CMMCorePlus.instance()
        self.model = hw_constants
        self.interceptor = ActionInterceptor(self.mmc, self.model)
        self.engine: PLogicMDAEngine | None = None

        self.interceptor.override_actions()
        self.view = MainView()
        self._setup_connections()

    def run(self) -> int:
        """Shows the main view and starts the application event loop."""
        return self.view.show()

    def _setup_connections(self) -> None:
        """
        Initializes and connects all non-view components of the application.
        """
        if not self._initialize_hardware():
            logger.critical("Hardware initialization failed.")

        # Enable the SPIM beam once on startup.
        logger.info("Enabling SPIM beam for the session.")
        set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "Yes")

        self._disconnect_faulty_snap_handler()
        self._initialize_mda_engine()
        self._connect_signals()
        logger.info("Application setup complete.")

    def _disconnect_faulty_snap_handler(self) -> None:
        """
        Disconnect the image preview's snap handler to prevent the race condition.
        """
        try:
            manager = self.view.window._viewers_manager
            # Creating the preview widget also makes it listen to imageSnapped.
            preview_widget = manager._create_or_show_img_preview()
            if preview_widget:
                # We disconnect its `append` slot, which calls the problematic `getImage`.
                self.mmc.events.imageSnapped.disconnect(preview_widget.append)
            logger.info("Successfully disconnected faulty preview snap handler.")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.warning("Could not disconnect faulty snap handler: %s", e)

    def _initialize_hardware(self) -> bool:
        """Runs the main hardware initialization sequence."""
        return initialize_system_hardware(self.mmc, self.model)

    def _initialize_mda_engine(self) -> None:
        """Sets up the custom MDA engine."""
        mda_widget = self.view.mda_widget()
        if not mda_widget:
            logger.warning("Could not find MDA widget to set up engine.")
            return
        self.engine = setup_mda_widget(mda_widget, self.mmc, self.model)
        self._connect_viewer_sliders()

    def _connect_signals(self) -> None:
        """Connects application-wide signals, like shutdown events."""
        if app := self.view.app():
            app.aboutToQuit.connect(self._on_exit)

    def _connect_viewer_sliders(self) -> None:
        """Connects the main viewer's events to the display update slot."""
        try:
            self.view.window._viewers_manager.mdaViewerCreated.connect(self._on_viewer_created)
            logger.info("Ready to connect sliders upon viewer creation.")
        except AttributeError as e:
            logger.error("Could not connect to viewer creation signal: %s", e)

    def _on_viewer_created(self, viewer: Any) -> None:
        """Once the viewer is created, connect its sliders to our handler."""
        if hasattr(viewer, "t_slider") and viewer.t_slider:
            viewer.t_slider.valueChanged.connect(functools.partial(self._on_slider_moved, viewer))
        if hasattr(viewer, "z_slider") and viewer.z_slider:
            viewer.z_slider.valueChanged.connect(functools.partial(self._on_slider_moved, viewer))
        try:
            self.view.window._viewers_manager.mdaViewerCreated.disconnect(self._on_viewer_created)
        except (TypeError, RuntimeError):
            pass

    def _on_slider_moved(self, viewer: Any) -> None:
        """Handle slider movements to update the displayed slice."""
        if not self.engine:
            return
        t_val = viewer.t_slider.value() if hasattr(viewer, "t_slider") and viewer.t_slider else 0
        z_val = viewer.z_slider.value() if hasattr(viewer, "z_slider") and viewer.z_slider else 0
        self.engine.set_displayed_slice(t_val, z_val)

    def _on_exit(self) -> None:
        """Clean up hardware state and restore actions on application exit."""
        logger.info("Application closing. Cleaning up hardware.")
        set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        self.interceptor.restore_actions()
        logger.info("Cleanup complete.")
