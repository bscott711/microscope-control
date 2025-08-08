# src/microscope/hardware/initializer.py
"""
Performs one-time system hardware initialization at application startup.
"""

import logging
from collections.abc import Callable

from pymmcore_plus import CMMCorePlus

from ..model.hardware_model import HardwareConstants
from .camera import check_and_reset_camera_trigger_modes
from .plogic import open_global_shutter

logger = logging.getLogger(__name__)


def _check_all_camera_triggers(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Adapter for check_and_reset_camera_trigger_modes to return a single bool.

    This function is successful only if all cameras were successfully tested.
    """
    results = check_and_reset_camera_trigger_modes(mmc, hw)
    if not results:
        # This case occurs if no camera devices were found to be checked.
        # We can consider this a non-failing state for initialization.
        logger.warning("No cameras were checked in check_and_reset_camera_trigger_modes.")
        return True
    # `all(results.values())` is True only if every camera returned True.
    return all(results.values())


def initialize_system_hardware(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Run all one-time hardware setup routines.

    This function is called once when the application starts to ensure that
    the hardware is in a known, ready state. It executes a sequence of
    initialization steps and returns whether all were successful.

    Args:
        mmc: The Micro-Manager core instance.
        hw: The hardware constants data model.

    Returns:
        True if all initialization steps succeeded, False otherwise.
    """
    logger.debug("Performing one-time system hardware initialization...")

    # A list of (name, function) tuples makes logging clear and is extensible.
    # All functions in the list must match the signature: (mmc, hw) -> bool.
    initialization_steps: list[tuple[str, Callable[[CMMCorePlus, HardwareConstants], bool]]] = [
        ("Opening global shutter", open_global_shutter),
        ("Verifying camera trigger modes", _check_all_camera_triggers),
    ]

    for step_name, step_func in initialization_steps:
        logger.debug(f"Executing initialization step: {step_name}...")
        try:
            if not step_func(mmc, hw):
                logger.critical(
                    f"Hardware initialization failed at step: '{step_name}'. The system may not be in a valid state.",
                )
                return False
        except Exception as e:
            logger.critical(
                f"An unexpected error occurred during step '{step_name}': {e}",
                exc_info=True,
            )
            return False

    logger.debug("System hardware initialization completed successfully.")
    return True
