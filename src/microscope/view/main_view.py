# microscope/view/main_view.py
"""
Main GUI View for the microscope application.
"""

import logging
import sys
from typing import Any

from pymmcore_gui import create_mmgui
from pymmcore_gui._main_window import MicroManagerGUI
from qtpy.QtWidgets import QApplication

# Set up logger
logger = logging.getLogger(__name__)


class MainView:
    """
    The main view for the microscope application.
    This class is responsible for creating, displaying, and providing access
    to the main GUI window and its widgets. It holds no application logic.
    """

    def __init__(self):
        # Let create_mmgui handle the creation of the MMQApplication instance.
        logger.info("Creating main GUI window.")
        self.window: MicroManagerGUI = create_mmgui(exec_app=False)
        self._app = QApplication.instance()  # Get the instance created by create_mmgui

    def get_widget(self, widget_key: str) -> Any:
        """Get a specific widget from the main window."""
        return self.window.get_widget(widget_key)

    def show(self):
        """Show the main window and start the application event loop."""
        logger.info("Showing main window.")
        self.window.show()
        if self._app:
            sys.exit(self._app.exec_())

    def app(self) -> QApplication | None:
        """Return the QApplication instance."""
        return self._app  # type: ignore
