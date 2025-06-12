# src/microscope/__main__.py
"""
Main application launch script for the Microscope Control package.

This script sets up the Qt Application and initializes the main window.
It now includes a command-line argument to launch in demo mode.
"""

import argparse
import sys

from PySide6.QtWidgets import QApplication

# Import the main GUI class
from .gui import AcquisitionGUI


def main():
    """Initializes and runs the Qt application."""
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Microscope Control Application")
    parser.add_argument("--demo", action="store_true", help="Run the application in demo mode")
    args = parser.parse_args()

    # Start the Qt App
    app = QApplication(sys.argv)
    # Create an instance of our main GUI window, passing the demo flag
    window = AcquisitionGUI(demo_mode=args.demo)
    # Show the window
    window.show()
    # Start the Qt event loop
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
