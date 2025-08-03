# src/microscope/main.py
"""Main entry point for the microscope application."""

import logging
import sys

from microscope.controller.application_controller import ApplicationController


def main():
    """Initializes and runs the main application controller."""
    # --- CENTRALIZED LOGGING CONFIGURATION ---
    # Set up the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Create a handler (e.g., StreamHandler for console output)
    handler = logging.StreamHandler(sys.stdout)

    # Define the format
    formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    # Add the handler to the root logger
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    # --- END CENTRALIZED LOGGING CONFIGURATION ---

    # Now, all loggers created with logging.getLogger(__name__) will inherit this configuration.
    logger = logging.getLogger(__name__)

    try:
        logger.info("Application starting...")
        controller = ApplicationController()
        controller.run()
    except Exception as e:
        # Use the root logger to ensure the critical message is always seen
        logging.critical("Application failed to start: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
