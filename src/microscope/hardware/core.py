# src/microscope/hardware/core.py
"""
core.py
Core utility functions for direct hardware communication.
These functions provide the low-level interface to the Micro-Manager core
and the ASI Tiger controller, used by all other hardware-specific modules.
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

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
        mmc: The CMMCorePlus instance.
        device_label: The label of the device in Micro-Manager.
        property_name: The name of the property to retrieve.

    Returns:
        The property value as a string if found, otherwise None.
    """
    if device_label not in mmc.getLoadedDevices():
        logger.warning(f"Device '{device_label}' not loaded; cannot get property.")
        return None
    if not mmc.hasProperty(device_label, property_name):
        logger.warning(f"Property '{property_name}' not found on '{device_label}'.")
        return None

    val = mmc.getProperty(device_label, property_name)
    logger.debug(f"Got {device_label}.{property_name} = {val}")
    return val


def set_property(
    mmc: CMMCorePlus, device_label: str, property_name: str, value: Any
) -> bool:
    """
    Sets a Micro-Manager device property, checking for existence and changes.

    This function will only send the set command if the new value is
    different from the current value. It returns True if the property has the
    desired value after execution, and False if an error occurred.

    Args:
        mmc: The CMMCorePlus instance.
        device_label: Label of the device.
        property_name: Name of the property.
        value: Desired value for the property.

    Returns:
        True if the property is successfully set to the desired value (or was
        already set). False if the device/property is not found or if the
        set command fails.
    """
    if device_label not in mmc.getLoadedDevices():
        logger.error(f"Device '{device_label}' not loaded; cannot set property.")
        return False
    if not mmc.hasProperty(device_label, property_name):
        logger.error(f"Property '{property_name}' not found on '{device_label}'.")
        return False

    current_value = mmc.getProperty(device_label, property_name)
    if current_value == str(value):
        logger.debug(f"{device_label}.{property_name} already set to {value}.")
        return True  # The state is correct, no action needed.

    try:
        mmc.setProperty(device_label, property_name, value)
        logger.debug(f"Set {device_label}.{property_name} = {value}")
        return True
    except Exception as e:
        logger.error(f"Failed to set {device_label}.{property_name} to {value}: {e}")
        return False


def send_tiger_command(mmc: CMMCorePlus, cmd: str, hw: "HardwareConstants") -> bool:
    """
    Sends a serial command to the TigerCommHub device.

    Args:
        mmc: The CMMCorePlus instance.
        cmd: The serial command string to send.
        hw: The HardwareConstants object providing the device label.

    Returns:
        True if the command was sent successfully, False otherwise.
    """
    tiger_label = hw.tiger_comm_hub_label
    if tiger_label not in mmc.getLoadedDevices():
        logger.error(f"Device '{tiger_label}' not loaded. Cannot send command: {cmd}")
        return False

    try:
        # Use the variable `tiger_label` for the device name.
        mmc.setProperty(tiger_label, "SerialCommand", cmd)
        logger.debug(f"Tiger command sent: {cmd}")
        # A short pause is often necessary for serial devices to process a command.
        time.sleep(0.01)
        return True
    except Exception as e:
        logger.error(f"Failed to send Tiger command: {cmd} - {e}", exc_info=True)
        return False
