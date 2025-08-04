# microscope/view/main_view.py
"""
Main GUI View for the microscope application.

This module defines the MainView class, which serves as a high-level facade
for the main GUI window provided by pymmcore-gui. Its primary role is to
instantiate and manage the window and provide a clean, type-safe interface
for controllers to access key widgets. It intentionally contains no business
or application logic.
"""

import logging
from typing import Any, cast

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_gui._main_window import MicroManagerGUI
from pymmcore_widgets.mda import MDAWidget
from qtpy.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class MainView:
    """
    A facade for the main GUI window, providing convenient, type-safe access.

    This class wraps the MicroManagerGUI window, offering specialized methods
    to access important child widgets, abstracting away the need for other
    parts of the app to know the specific keys or types of the widgets.
    """

    def __init__(self) -> None:
        """Initializes the main window and application instance."""
        logger.info("Creating main GUI window.")
        # Let create_mmgui handle the creation of the QApplication instance.
        self.window: MicroManagerGUI = create_mmgui(exec_app=False)
        # We must cast the instance() result to the more specific QApplication
        # to satisfy the static type checker.
        self._app: QApplication | None = cast(QApplication, QApplication.instance())

    def mda_widget(self) -> MDAWidget | None:
        """
        Return the Multi-Dimensional Acquisition (MDA) widget, if it exists.

        This provides a convenient, type-safe way to access the MDA widget
        without needing to know its specific lookup key.

        Returns:
            The MDAWidget instance, or None if not found.
        """
        # WidgetAction is an Enum, so we use .value to get the string key.
        widget = self.window.get_widget(WidgetAction.MDA_WIDGET.value)
        if isinstance(widget, MDAWidget):
            return widget
        logger.warning("MDA widget not found in the main window.")
        return None

    def get_widget(self, widget_key: str) -> Any:
        """
        Get a specific widget from the main window by its string key.

        Args:
            widget_key: The key of the widget to retrieve.

        Returns:
            The widget instance (typed as Any), or None if not found.
        """
        return self.window.get_widget(widget_key)

    def show(self) -> int:
        """
        Show the main window and start the application event loop.

        Note: This is a blocking call that will not return until the
        application is closed. The return value is the application's exit code.

        Returns:
            The application's exit code.
        """
        logger.info("Showing main window and starting event loop.")
        self.window.show()
        if self._app:
            return self._app.exec()
        return 0

    def app(self) -> QApplication | None:
        """Return the QApplication instance."""
        return self._app
