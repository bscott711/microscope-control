# src/microscope/main.py
"""
Main entry point for the microscope application.
"""

import logging
import sys

from microscope.controller.application_controller import ApplicationController


def main():
    """Initializes and runs the main application controller."""
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

    try:
        controller = ApplicationController()
        controller.run()
    except Exception as e:
        logger.critical("Application failed to start: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
