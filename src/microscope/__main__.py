# src/microscope/__main__.py
"""
Main application launch script for the Microscope Control package.

This script sets up the Qt Application and initializes the main window.
"""

import sys

from PySide6.QtWidgets import QApplication

# Import the main GUI class
from .gui import AcquisitionGUI


def main():
    """Initializes and runs the Qt application."""
    app = QApplication(sys.argv)
    # Create an instance of our main GUI window
    window = AcquisitionGUI()
    # Show the window
    window.show()
    # Start the Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
