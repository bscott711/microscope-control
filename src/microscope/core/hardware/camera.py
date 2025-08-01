# src/microscope/core/hardware/camera.py

"""
Functions for configuring cameras.
"""

import logging

from pymmcore_plus import CMMCorePlus

from ..constants import HardwareConstants
from .utils import set_property

logger = logging.getLogger(__name__)


def set_camera_trigger_mode_level_high(
    mmc: CMMCorePlus, hw: HardwareConstants, desired_modes=("Level Trigger", "Edge Trigger")
) -> dict[str, bool]:
    """Sets the camera trigger mode for all specified cameras."""
    results = {}
    camera_labels = [hw.camera_a_label, hw.camera_b_label]

    for camera_label in camera_labels:
        if camera_label not in mmc.getLoadedDevices():
            continue
        if not mmc.hasProperty(camera_label, "TriggerMode"):
            logger.warning(f"Camera '{camera_label}' does not support TriggerMode.")
            results[camera_label] = False
            continue

        allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
        success = False
        for mode in desired_modes:
            if mode in allowed:
                set_property(mmc, camera_label, "TriggerMode", mode)
                success = True
                break

        if success:
            set_property(mmc, camera_label, "TriggerMode", "Internal Trigger")
            logger.info(f"Successfully cycled trigger mode for {camera_label}.")
            results[camera_label] = True
        else:
            logger.warning(f"Could not set a desired trigger mode for {camera_label}.")
            results[camera_label] = False

    return results


def set_camera_for_hardware_trigger(mmc: CMMCorePlus, camera_label: str) -> bool:
    """Sets a camera to the correct external trigger mode for an acquisition."""
    if camera_label not in mmc.getLoadedDevices():
        logger.error(f"Camera '{camera_label}' not loaded.")
        return False
    if not mmc.hasProperty(camera_label, "TriggerMode"):
        logger.warning(f"Camera '{camera_label}' does not support TriggerMode.")
        return False

    allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
    for mode in ("Level Trigger", "Edge Trigger"):
        if mode in allowed:
            set_property(mmc, camera_label, "TriggerMode", mode)
            logger.info(f"Set {camera_label} TriggerMode to '{mode}'.")
            return True

    logger.error(f"Could not find a suitable external trigger mode for {camera_label}.")
    return False
