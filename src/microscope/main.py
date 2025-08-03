# src/microscope/main.py
"""Main entry point for the microscope application."""

import argparse
import logging
import sys
from pathlib import Path

from microscope.controller.application_controller import ApplicationController
from microscope.model.hardware_model import HardwareConstants


def main():
    """Initializes and runs the main application controller."""
    # --- Parse Command Line Arguments ---
    parser = argparse.ArgumentParser(description="OPM Control System")
    parser.add_argument(
        "--config",
        type=Path,
        default="hardware_profiles/default_config.yml",
        help="Path to the YAML configuration file (default: default_config.yml)",
    )
    args = parser.parse_args()

    # --- CENTRALIZED LOGGING CONFIGURATION ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    if not root_logger.handlers:
        root_logger.addHandler(handler)

    logger = logging.getLogger(__name__)
    logger.info("Application starting...")

    try:
        # Create HardwareConstants with the specified config file
        hw_constants = HardwareConstants(config_path=args.config)

        # Pass the config to the controller
        controller = ApplicationController(hw_constants)
        controller.run()
    except Exception as e:
        logging.critical("Application failed to start: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
