# src/microscope/hardware/core.py
"""
core.py
Core utility functions for direct hardware communication.
These functions provide the low-level interface to the Micro-Manager core
and the ASI Tiger controller, used by all other hardware-specific modules.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional

from pymmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from microscope.model.hardware_model import HardwareConstants


# Set up logger
logger = logging.getLogger(__name__)


@contextmanager
def tiger_command_batch(mmc: CMMCorePlus, hw: "HardwareConstants") -> Iterator[None]:
    """
    Temporarily disables 'OnlySendSerialCommandOnChange' for a command batch.

    This context manager ensures that the Tiger controller hub will accept
    repeated serial commands, which is often necessary for programming cards
    like the PLogic. The original setting is always restored upon exit.
    """
    hub_label = hw.tiger_comm_hub_label
    prop_name = "OnlySendSerialCommandOnChange"
    original_setting = get_property(mmc, hub_label, prop_name)
    was_changed = original_setting == "Yes"

    if was_changed:
        set_property(mmc, hub_label, prop_name, "No")
    try:
        yield
    finally:
        if was_changed:
            logger.debug(f"Restoring {hub_label}.{prop_name} to '{original_setting}'.")
            set_property(mmc, hub_label, prop_name, original_setting)


def get_property(
    mmc: CMMCorePlus, device_label: str, property_name: str
) -> Optional[str]:
    """
    Safely gets a Micro-Manager device property value.
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
        return True

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
    """
    tiger_label = hw.tiger_comm_hub_label
    if tiger_label not in mmc.getLoadedDevices():
        logger.error(f"Device '{tiger_label}' not loaded. Cannot send command: {cmd}")
        return False

    try:
        mmc.setProperty(tiger_label, "SerialCommand", cmd)
        logger.debug(f"Tiger command sent: {cmd}")
        time.sleep(0.01)
        return True
    except Exception as e:
        logger.error(f"Failed to send Tiger command: {cmd} - {e}", exc_info=True)
        return False
