# src/microscope/main.py
"""Main entry point for the microscope application."""

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn

from microscope.controller.application_controller import ApplicationController
from microscope.model.hardware_model import HardwareConstants


def _setup_logging() -> None:
    """Configure root logger for the application."""
    root_logger = logging.getLogger()
    # Prevent adding duplicate handlers if this is ever called more than once.
    if root_logger.hasHandlers():
        return
    root_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Microscope Control System")
    parser.add_argument(
        "--config",
        type=Path,
        default="hardware_profiles/default_config.yml",
        help="Path to the YAML configuration file.",
    )
    return parser.parse_args()


def main() -> NoReturn:
    """
    Parse arguments, set up logging, and run the main application controller.
    """
    args = _parse_args()
    _setup_logging()

    logger = logging.getLogger(__name__)
    logger.info("Application starting with config: %s", args.config)

    try:
        hw_constants = HardwareConstants(config_path=args.config)
        controller = ApplicationController(hw_constants)
        # controller.run() starts the Qt event loop and returns an exit code.
        exit_code = controller.run()
    except Exception as e:
        logging.critical("Application failed to start: %s", e, exc_info=True)
        sys.exit(1)  # Exit with a failure code

    sys.exit(exit_code)  # Exit with the code from the application


if __name__ == "__main__":
    main()
