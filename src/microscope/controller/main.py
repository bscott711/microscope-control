import logging
import sys
from typing import Any

from pymmcore_gui import MicroManagerGUI, WidgetAction, create_mmgui
from pymmcore_gui.widgets.image_preview._ndv_preview import NDVPreview
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

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

    def __init__(self, app: QApplication, window: MicroManagerGUI):
        self.app = app
        self.window = window
        self.mmc = CMMCorePlus.instance()
        self.hw = HardwareConstants()
        self._safe_preview_callback: Any = None

        # Defer hardware and related GUI setup until the system configuration is loaded
        self.mmc.events.systemConfigurationLoaded.connect(self._on_system_config_loaded)

        # Instantiate sub-controllers
        self.actions_controller = ActionsController(self)
        self.mda_controller = MDAController(self)

        self._connect_signals()

    @classmethod
    def run(cls) -> int:
        """
        Class method to create the CMMCorePlus instance, GUI, and run the app.
        This is the main entry point for the application.
        """
        CMMCorePlus.instance()
        window = create_mmgui(exec_app=False)
        app = QApplication.instance()

        if not app:
            app = QApplication(sys.argv)

        if not isinstance(app, QApplication):
            sys.exit("Could not get a QApplication instance.")

        controller = cls(app, window)
        controller.show_window()
        return app.exec_()

    def _patch_preview_widget(self):
        """
        Find the default NDVPreview widget and patch its signal connections
        to prevent the 'Camera image buffer read failed' error.
        """
        viewer = getattr(self.window, "viewer", None)
        if not viewer:
            logger.warning("Could not find 'viewer' widget on main window.")
            return

        preview_widget = getattr(viewer, "view", None)
        if not isinstance(preview_widget, NDVPreview):
            logger.warning("Could not find 'NDVPreview' widget in viewer.view.")
            return

        # 1. Disconnect the original, problematic callback.
        # This is the most critical step to prevent the race condition.
        try:
            self.mmc.events.imageSnapped.disconnect(preview_widget._on_image_snapped)
            logger.info("Successfully disconnected original preview's slot.")
        except (TypeError, RuntimeError):
            # It might already be disconnected in some cases, which is fine.
            logger.warning("Could not disconnect original preview slot.")
            pass

        # 2. Define and connect a new, safe callback to the correct signal.
        def _on_frame_ready(image: Any, metadata: dict) -> None:
            if not preview_widget.use_with_mda and preview_widget._is_mda_running:
                return
            preview_widget.append(image)

        # 3. Store a reference to the callback to prevent garbage collection.
        self._safe_preview_callback = _on_frame_ready
        self.mmc.events.frameReady.connect(self._safe_preview_callback)
        logger.info("Patched preview widget with safe frameReady callback.")

    def _on_system_config_loaded(self):
        """
        Initializes hardware and patches the GUI after the config is loaded.
        """
        logger.info("System configuration loaded. Setting up hardware...")
        self._patch_preview_widget()
        open_global_shutter(self.mmc, self.hw)
        set_camera_trigger_mode_level_high(self.mmc, self.hw)
        engine = CustomPLogicMDAEngine()
        self.mmc.register_mda_engine(engine)
        logger.info("Hardware setup complete. Custom PLogic MDA Engine registered.")

    def _connect_signals(self):
        """Connects UI signals to controller slots."""
        self.actions_controller.connect_signals()

        mda_widget = self.window.get_widget(WidgetAction.MDA_WIDGET)
        if mda_widget:
            mda_widget.execute_mda = self.mda_controller.run_mda
            logger.info("MDA 'Run' button has been wired to the MDA controller.")
        else:
            logger.warning("Could not find MDA widget to intercept.")

        self.app.aboutToQuit.connect(self._on_exit)

    def show_window(self):
        """Shows the main application window."""
        self.window.show()

    def _on_exit(self):
        """Clean up hardware state when the application quits."""
        logger.info("Application closing. Cleaning up hardware state.")
        self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.hw)
        self.actions_controller.cleanup()
        logger.info("Application cleanup complete.")
