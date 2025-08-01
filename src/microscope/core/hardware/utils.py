# src/microscope/core/hardware/utils.py

"""
Generic utility functions for interacting with Micro-Manager devices,
especially the ASI Tiger controller.
"""

import logging
import time
from typing import Optional

from pymmcore_plus import CMMCorePlus

logger = logging.getLogger(__name__)


def get_property(mmc: CMMCorePlus, device_label: str, property_name: str) -> Optional[str]:
    """Safely gets a Micro-Manager device property value."""
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        return mmc.getProperty(device_label, property_name)
    logger.warning(f"Property '{property_name}' not found on '{device_label}'")
    return None


def set_property(mmc: CMMCorePlus, device_label: str, property_name: str, value: str) -> bool:
    """Sets a Micro-Manager device property only if it has changed."""
    if device_label not in mmc.getLoadedDevices():
        logger.error(f"Device '{device_label}' not loaded.")
        return False
    if not mmc.hasProperty(device_label, property_name):
        logger.error(f"Property '{property_name}' not found on '{device_label}'.")
        return False

    if mmc.getProperty(device_label, property_name) != str(value):
        try:
            mmc.setProperty(device_label, property_name, value)
            return True
        except Exception as e:
            logger.error(f"Failed to set {device_label}.{property_name} = {value}: {e}")
            return False
    return True  # Return True if already set to the correct value


def send_tiger_command(mmc: CMMCorePlus, cmd: str) -> bool:
    """Sends a serial command to the TigerCommHub device."""
    if "TigerCommHub" not in mmc.getLoadedDevices():
        logger.error(f"TigerCommHub not loaded. Cannot send command: {cmd}")
        return False
    try:
        mmc.setProperty("TigerCommHub", "SerialCommand", cmd)
        time.sleep(0.01)  # Small delay for command processing
        return True
    except Exception as e:
        logger.error(f"Failed to send Tiger command: {cmd} - {e}")
        return False
