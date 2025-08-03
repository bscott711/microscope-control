# src/microscope/hardware/initializer.py
"""
Performs one-time system hardware initialization at application startup.
"""

import logging

from pymmcore_plus import CMMCorePlus

from ..model.hardware_model import HardwareConstants
from .camera import set_camera_trigger_mode_level_high
from .plogic import open_global_shutter

logger = logging.getLogger(__name__)


def initialize_system_hardware(mmc: CMMCorePlus, hw: HardwareConstants) -> None:
    """
    Run all one-time hardware setup routines.

    This function is called once when the application starts to ensure that
    the hardware is in a known, ready state.

    Args:
        mmc: The Micro-Manager core instance.
        hw: The hardware constants data model.
    """
    logger.info("Performing one-time system hardware initialization...")
    try:
        open_global_shutter(mmc, hw)
        set_camera_trigger_mode_level_high(mmc, hw)
        logger.info("System hardware initialization complete.")
    except Exception as e:
        logger.critical("Failed during system hardware initialization: %s", e, exc_info=True)
        # Depending on desired behavior, one might want to re-raise or exit here
