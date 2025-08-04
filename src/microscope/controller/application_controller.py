# src/microscope/controller/application_controller.py
"""
Main application controller for the microscope.

This module contains the primary controller that orchestrates the startup,
interconnectivity, and shutdown of all application components, including the
view, model, hardware drivers, and event interceptors.
"""

import logging
from functools import partial
from typing import Any, Optional

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

    Orchestrates the View, Model, services (like ActionInterceptor), and
    hardware initialization. It wires all components together and manages
    the application's lifecycle.
    """

    def __init__(self, hw_constants: HardwareConstants):
        self.mmc = CMMCorePlus.instance()
        self.model = hw_constants
        self.view = MainView()
        self.interceptor = ActionInterceptor(self.mmc, self.model)
        self.engine: Optional[PLogicMDAEngine] = None
        self._setup_application()

    def run(self) -> int:
        """Shows the main view and starts the application event loop."""
        return self.view.show()

    def _setup_application(self) -> None:
        """
        Initializes and connects all components of the application.
        """
        if not self._initialize_hardware():
            logger.critical("Hardware initialization failed. Application may be unstable.")

        self._patch_gui_actions()
        self._initialize_mda_engine()
        self._connect_signals()
        logger.info("Application setup complete.")

    def _initialize_hardware(self) -> bool:
        """Runs the main hardware initialization sequence."""
        return initialize_system_hardware(self.mmc, self.model)

    def _patch_gui_actions(self) -> None:
        """Applies patches and workarounds for core GUI actions."""
        self._disconnect_faulty_snap_handler()
        self._disconnect_faulty_property_handler()
        self.interceptor.wrap_snap_action()
        self.interceptor.wrap_toggle_live_action()

    def _initialize_mda_engine(self) -> None:
        """Sets up the custom MDA engine and connects viewer sliders."""
        # Use the type-safe accessor from the MainView
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
            # FIX: Use the 'mdaViewerCreated' signal, which we discovered
            # is the correct name for the installed library version.
            self.view.window._viewers_manager.mdaViewerCreated.connect(  # type: ignore
                self._on_viewer_created
            )
            logger.info("Ready to connect sliders upon viewer creation.")
        except AttributeError as e:
            logger.error("Could not connect to viewer creation signal: %s", e)

    def _on_viewer_created(self, viewer: Any) -> None:
        """Once the viewer is created, connect its sliders to our handler."""
        # This is the original, working slider connection logic.
        if hasattr(viewer, "t_slider") and viewer.t_slider:
            viewer.t_slider.valueChanged.connect(partial(self._on_slider_moved, viewer))
            logger.info("Viewer T-slider connected for live scrubbing.")
        if hasattr(viewer, "z_slider") and viewer.z_slider:
            viewer.z_slider.valueChanged.connect(partial(self._on_slider_moved, viewer))
            logger.info("Viewer Z-slider connected for live scrubbing.")

        # Disconnect to prevent multiple connections if a new viewer is made.
        try:
            # FIX: Use the correct 'mdaViewerCreated' signal name here as well.
            self.view.window._viewers_manager.mdaViewerCreated.disconnect(  # type: ignore
                self._on_viewer_created
            )
        except (TypeError, RuntimeError):
            pass

    def _on_slider_moved(self, viewer: Any) -> None:
        """Handle slider movements to update the displayed slice."""
        if not self.engine:
            return

        t = viewer.t_slider.value() if hasattr(viewer, "t_slider") and viewer.t_slider else 0
        z = viewer.z_slider.value() if hasattr(viewer, "z_slider") and viewer.z_slider else 0

        self.engine.set_displayed_slice(t, z)

    def _disconnect_faulty_snap_handler(self) -> None:
        """Workaround: Disconnect the default snap handler from the preview widget."""
        try:
            manager = self.view.window._viewers_manager
            preview_widget = manager._create_or_show_img_preview()
            if preview_widget:
                self.mmc.events.imageSnapped.disconnect(preview_widget.append)
            logger.info("Successfully disconnected preview widget's snap handler.")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.warning("Could not disconnect faulty snap handler: %s", e)

    def _disconnect_faulty_property_handler(self) -> None:
        """Workaround: Disconnect a default property handler that can cause errors."""
        try:
            manager = self.view.window._viewers_manager
            self.mmc.events.propertyChanged.disconnect(manager._on_property_changed)
            logger.info("Successfully disconnected faulty propertyChanged handler.")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.warning("Could not disconnect faulty propertyChanged handler: %s", e)

    def _on_exit(self) -> None:
        """Clean up hardware state and restore actions on application exit."""
        logger.info("Application closing. Cleaning up hardware and restoring actions.")
        set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        self.interceptor.restore_actions()
        logger.info("Cleanup complete.")
