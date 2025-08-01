# microscope/view/main_view.py
"""
Main GUI View for the microscope application.
"""

import logging
import sys
from typing import Any

from pymmcore_gui import create_mmgui
from pymmcore_gui._main_window import MicroManagerGUI  # Corrected import
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
        # Ensure a QApplication instance exists.
        app = QApplication.instance()
        if not app:
            self._app = QApplication(sys.argv)
        else:
            self._app = app

        logger.info("Creating main GUI window.")
        # Corrected type hint to MicroManagerGUI
        self.window: MicroManagerGUI = create_mmgui(exec_app=False)

    def get_widget(self, widget_key: str) -> Any:
        """
        Get a specific widget from the main window.

        Args:
            widget_key: The key corresponding to the desired widget
                        (e.g., from pymmcore_gui.WidgetAction).

        Returns:
            The requested widget, or None if not found.
        """
        return self.window.get_widget(widget_key)

    def show(self):
        """Show the main window and start the application event loop."""
        logger.info("Showing main window.")
        self.window.show()
        sys.exit(self._app.exec_())

    def app(self) -> QApplication:
        """Return the QApplication instance."""
        # This assert reassures the type checker that self._app is a QApplication
        # based on the logic in __init__.
        assert isinstance(self._app, QApplication)
        return self._app
