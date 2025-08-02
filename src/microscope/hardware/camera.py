# src/microscope/hardware/camera.py
"""
camera.py
Functions for configuring and controlling camera devices.
This module handles all aspects of setting up camera trigger modes
and preparing the camera for hardware-timed acquisitions.
"""

import logging

from pymmcore_plus import CMMCorePlus

from microscope.model.hardware_model import HardwareConstants

from .core import set_property

# Set up logger
logger = logging.getLogger(__name__)


def set_camera_trigger_mode_level_high(
    mmc: CMMCorePlus, hw: HardwareConstants, desired_modes=("Level Trigger", "Edge Trigger")
) -> dict[str, bool]:
    """
    Sets the camera trigger mode for all specified cameras.
    Iterates through camera labels defined in the hardware constants,
    attempts to set a desired trigger mode, and then reverts to 'Internal Trigger'.
    Args:
        mmc: Core instance
        hw: Hardware constants object
        desired_modes: A tuple of acceptable trigger modes.
    Returns:
        A dictionary where keys are camera labels and values are booleans
        indicating if the full sequence of setting and reverting was successful.
    """
    results = {}
    # Create a list of all cameras to configure
    camera_labels = [hw.camera_a_label, hw.camera_b_label]

    for camera_label in camera_labels:
        # Skip if the camera isn't loaded
        if camera_label not in mmc.getLoadedDevices():
            logger.warning(f"Camera '{camera_label}' not loaded, skipping.")
            continue

        # Check for TriggerMode property
        if not mmc.hasProperty(camera_label, "TriggerMode"):
            logger.warning(f"Camera '{camera_label}' does not support TriggerMode.")
            results[camera_label] = False
            continue

        allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
        success = False

        # First, try to set one of the desired external trigger modes
        for mode in desired_modes:
            if mode in allowed:
                try:
                    mmc.setProperty(camera_label, "TriggerMode", mode)
                    logger.info(f"Set {camera_label} TriggerMode to '{mode}'.")
                    success = True
                    break  # Mode set, exit the inner loop
                except Exception as e:
                    logger.error(f"Failed to set {camera_label} to '{mode}': {e}")

        if not success:
            logger.warning(f"None of {desired_modes} found for {camera_label}.")
            results[camera_label] = False
            continue

        # Always revert to "Internal Trigger" to leave the camera in a ready state
        internal_mode = "Internal Trigger"
        if internal_mode in allowed:
            try:
                mmc.setProperty(camera_label, "TriggerMode", internal_mode)
                logger.info(f"Reverted {camera_label} TriggerMode to '{internal_mode}'.")
                results[camera_label] = True
            except Exception as e:
                logger.error(f"Failed to revert {camera_label} to '{internal_mode}': {e}")
                results[camera_label] = False  # The operation failed if we can't revert
        else:
            logger.warning(f"'{internal_mode}' is not supported for {camera_label}.")
            results[camera_label] = False

    return results


def set_camera_for_hardware_trigger(mmc: CMMCorePlus, camera_label: str) -> bool:
    """
    Sets a camera to the correct external trigger mode for an acquisition.
    Args:
        mmc: Core instance
        camera_label: Label of the camera to configure
    Returns:
        True if successfully configured, False otherwise
    """
    logger.info(f"Setting {camera_label} to external trigger mode for acquisition.")

    if camera_label not in mmc.getLoadedDevices():
        logger.error(f"Camera '{camera_label}' not loaded.")
        return False

    if not mmc.hasProperty(camera_label, "TriggerMode"):
        logger.warning(f"Camera '{camera_label}' does not support TriggerMode.")
        return False

    allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")

    # Prefer "Level Trigger" as it's often used for constant-exposure acquisitions
    for mode in ("Level Trigger", "Edge Trigger"):
        if mode in allowed:
            set_property(mmc, camera_label, "TriggerMode", mode)
            logger.info(f"Set {camera_label} TriggerMode to '{mode}'.")
            return True

    logger.error(f"Could not find a suitable external trigger mode for {camera_label}.")
    return False
