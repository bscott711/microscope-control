# src/microscope/controller/application_controller.py
"""
Main application controller for the microscope.
A thin orchestrator that wires components together.
"""

import logging
from functools import partial
from typing import Optional

from pymmcore_gui import WidgetAction
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

    Orchestrates the View, Model, and services like the ActionInterceptor
    and HardwareInitializer.
    """

    def __init__(self, hw_constants: HardwareConstants):
        self.mmc = CMMCorePlus.instance()
        self.model = hw_constants
        self.view = MainView()
        self.interceptor = ActionInterceptor(self.mmc, self.model)
        self.engine: Optional[PLogicMDAEngine] = None
        self._setup_logic()

    def run(self) -> None:
        """Starts the application by showing the main view."""
        self.view.show()

    def _setup_logic(self) -> None:
        """Wire up all the application logic."""
        self._disconnect_faulty_snap_handler()
        self._disconnect_faulty_property_handler()

        # Use the dedicated interceptor to wrap actions
        self.interceptor.wrap_snap_action()
        self.interceptor.wrap_toggle_live_action()

        # Use the dedicated hardware initializer
        initialize_system_hardware(self.mmc, self.model)

        # Use the dedicated MDA setup service
        mda_widget = self.view.get_widget(WidgetAction.MDA_WIDGET)
        if mda_widget:
            # NOTE: This requires setup_mda_widget to return the engine instance
            self.engine = setup_mda_widget(mda_widget, self.mmc, self.model)
            self._connect_viewer_sliders()
        else:
            logger.warning("Could not find MDA widget to intercept.")

        # Connect app cleanup
        if app := self.view.app():
            app.aboutToQuit.connect(self._on_exit)

    def _connect_viewer_sliders(self) -> None:
        """Connect the main viewer's T and Z sliders to the display update slot."""
        # The main_viewer may not exist right at startup, so we connect lazily
        # by listening for the first time a viewer is created.
        try:
            # Pylance may not find viewer_created due to the dynamic nature of Qt
            # signals, so we ignore the type error. This is the correct signal name.
            self.view.window._viewers_manager.viewer_created.connect(  # type: ignore
                self._on_viewer_created
            )
            logger.info("Ready to connect sliders upon viewer creation.")
        except Exception as e:
            logger.error("Could not connect to viewer_created signal: %s", e)

    def _on_viewer_created(self, viewer) -> None:
        """Once the viewer is created, connect its sliders to our handler."""
        if viewer.t_slider:
            # Use partial to pass the specific viewer instance to the handler
            viewer.t_slider.valueChanged.connect(partial(self._on_slider_moved, viewer))
            logger.info("Viewer T-slider connected for live scrubbing.")
        if viewer.z_slider:
            viewer.z_slider.valueChanged.connect(partial(self._on_slider_moved, viewer))
            logger.info("Viewer Z-slider connected for live scrubbing.")

        # Disconnect to prevent multiple connections if a new viewer is made.
        try:
            # Pylance may not find viewer_created due to the dynamic nature of Qt
            # signals, so we ignore the type error. This is the correct signal name.
            self.view.window._viewers_manager.viewer_created.disconnect(  # type: ignore
                self._on_viewer_created
            )
        except (TypeError, RuntimeError):  # It might already be disconnected
            pass

    def _on_slider_moved(self, viewer) -> None:
        """Handle slider movements to update the displayed slice."""
        # If the engine exists, always try to update the display.
        # The engine itself handles cases where the frame buffer is empty.
        if not self.engine:
            return

        t = viewer.t_slider.value() if viewer.t_slider else 0
        z = viewer.z_slider.value() if viewer.z_slider else 0

        self.engine.set_displayed_slice(t, z)

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

    def _disconnect_faulty_property_handler(self) -> None:
        """Disconnect the property changed handler to prevent AttributeError."""
        try:
            manager = self.view.window._viewers_manager
            # The problematic callback is a method of the ViewersManager instance
            # that is connected to the propertyChanged signal by default.
            self.mmc.events.propertyChanged.disconnect(manager._on_property_changed)
            logger.info("Successfully disconnected faulty propertyChanged handler.")
        except (AttributeError, TypeError, RuntimeError) as e:
            logger.error("Failed to disconnect faulty propertyChanged handler: %s", e)

    def _on_exit(self) -> None:
        """Clean up hardware state and restore actions on exit."""
        logger.info("Application closing. Cleaning up hardware.")
        set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        self.interceptor.restore_actions()
        logger.info("Cleanup complete.")
