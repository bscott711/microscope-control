# src/microscope/hardware/core.py
"""
core.py
Core utility functions for direct hardware communication.
These functions provide the low-level interface to the Micro-Manager core
and the ASI Tiger controller, used by all other hardware-specific modules.
"""

import logging
import time
from typing import TYPE_CHECKING, Optional

from pymmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from microscope.model.hardware_model import HardwareConstants


# Set up logger
logger = logging.getLogger(__name__)


def get_property(
    mmc: CMMCorePlus, device_label: str, property_name: str
) -> Optional[str]:
    """
    Safely gets a Micro-Manager device property value.

    Args:
        mmc: Core instance
        device_label: The label of the device in Micro-Manager.
        property_name: The name of the property to retrieve.

    Returns:
        The property value as a string if found, otherwise None.
    """
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        val = mmc.getProperty(device_label, property_name)
        logger.debug(f"Got {device_label}.{property_name} = {val}")
        return val
    logger.warning(f"Property '{property_name}' not found on '{device_label}'")
    return None


def set_property(
    mmc: CMMCorePlus, device_label: str, property_name: str, value: str
) -> bool:
    """
    Sets a Micro-Manager device property only if it has changed.

    Args:
        mmc: Core instance
        device_label: Label of the device.
        property_name: Name of the property.
        value: Desired value.

    Returns:
        True if successfully set, False otherwise.
    """
    if device_label not in mmc.getLoadedDevices():
        logger.error(f"Device '{device_label}' not loaded. Cannot set property.")
        return False
    if not mmc.hasProperty(device_label, property_name):
        logger.error(f"Property '{property_name}' not found on '{device_label}'.")
        return False

    current_value = mmc.getProperty(device_label, property_name)
    if current_value != str(value):
        try:
            mmc.setProperty(device_label, property_name, value)
            logger.debug(f"Set {device_label}.{property_name} = {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set {device_label}.{property_name} = {value}: {e}")
            return False
    else:
        logger.debug(f"{device_label}.{property_name} already set to {value}")
        return False


def send_tiger_command(
    mmc: CMMCorePlus, cmd: str, hw: "HardwareConstants"
) -> bool:
    """
    Sends a serial command to the TigerCommHub device.

    Args:
        mmc: Core instance
        cmd: Serial command to send.
        hw: HardwareConstants object

    Returns:
        True if command was sent, False otherwise.
    """
    tiger_label = hw.tiger_comm_hub_label

    if tiger_label not in mmc.getLoadedDevices():
        logger.error(f"TigerCommHub not loaded. Cannot send command: {cmd}")
        return False

    try:
        mmc.setProperty("TigerCommHub", "SerialCommand", cmd)
        logger.debug(f"Tiger command sent: {cmd}")
        time.sleep(0.01)
        return True
    except Exception as e:
        logger.error(f"Failed to send Tiger command: {cmd} - {e}", exc_info=True)
        return False
