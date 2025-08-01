# src/microscope/main.py

import logging
import sys

from qtpy.QtWidgets import QApplication

from microscope.controller import ApplicationController

# Set up logger
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


def main():
    """Initializes and runs the microscope control application."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    controller = ApplicationController(app)
    controller.show_window()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
