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

# Set up logger
logger = logging.getLogger(__name__)


def _set_camera_trigger_mode(mmc: CMMCorePlus, camera_label: str, mode: str) -> bool:
    """
    Sets the trigger mode for a single camera, performing all necessary checks.

    This is a low-level helper function.

    Args:
        mmc: The CMMCorePlus instance.
        camera_label: The device label of the camera to configure.
        mode: The desired trigger mode to set.

    Returns:
        True if the mode was set successfully, False otherwise.
    """
    if camera_label not in mmc.getLoadedDevices():
        logger.warning(f"Camera '{camera_label}' not loaded, skipping.")
        return False

    if not mmc.hasProperty(camera_label, "TriggerMode"):
        logger.warning(f"Camera '{camera_label}' does not support 'TriggerMode'.")
        return False

    allowed_modes = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
    if mode not in allowed_modes:
        logger.warning(
            f"Mode '{mode}' not supported by {camera_label}. Allowed modes: {list(allowed_modes)}",
        )
        return False

    try:
        mmc.setProperty(camera_label, "TriggerMode", mode)
        logger.info(f"Set {camera_label} 'TriggerMode' to '{mode}'.")
        return True
    except Exception as e:
        logger.error(f"Failed to set {camera_label} 'TriggerMode' to '{mode}': {e}")
        return False


def set_camera_for_hardware_trigger(
    mmc: CMMCorePlus,
    camera_label: str,
    preferred_modes: tuple[str, ...] = ("Level Trigger", "Edge Trigger"),
) -> bool:
    """
    Sets a camera to a suitable external trigger mode for an acquisition.

    It iterates through a list of preferred modes and sets the first one
    that the camera supports.

    Args:
        mmc: The CMMCorePlus instance.
        camera_label: Label of the camera to configure.
        preferred_modes: An ordered tuple of trigger modes to try.

    Returns:
        True if a suitable mode was successfully set, False otherwise.
    """
    logger.info(f"Configuring {camera_label} for hardware-timed acquisition.")
    for mode in preferred_modes:
        if _set_camera_trigger_mode(mmc, camera_label, mode):
            return True

    logger.error(
        f"Could not set a suitable trigger mode for {camera_label} from {preferred_modes}.",
    )
    return False


def check_and_reset_camera_trigger_modes(
    mmc: CMMCorePlus,
    hw: HardwareConstants,
    external_modes: tuple[str, ...] = ("Level Trigger", "Edge Trigger"),
    reset_mode: str = "Internal Trigger",
) -> dict[str, bool]:
    """
    Verifies cameras can use an external trigger, then reverts to a safe state.

    For each camera, this function attempts to set it to an external trigger
    mode and then immediately reverts it to a reset mode (e.g., 'Internal').
    This is useful for verifying hardware compatibility before an experiment.

    Args:
        mmc: The CMMCorePlus instance.
        hw: The hardware constants, providing camera labels.
        external_modes: A tuple of acceptable external trigger modes to test.
        reset_mode: The trigger mode to revert to after the test.

    Returns:
        A dictionary mapping camera labels to a boolean indicating if the full
        sequence (set external -> set reset) was successful.
    """
    results = {}
    camera_labels = [hw.camera_a_label, hw.camera_b_label]

    for camera_label in camera_labels:
        # Attempt to set one of the specified external modes
        was_set = False
        for mode in external_modes:
            # We only need to find one that works for the test
            if _set_camera_trigger_mode(mmc, camera_label, mode):
                was_set = True
                break

        if not was_set:
            logger.warning(f"Test failed: Could not set any of {external_modes} for {camera_label}.")
            results[camera_label] = False
            continue

        # If setting an external mode worked, revert to the safe/reset mode
        if _set_camera_trigger_mode(mmc, camera_label, reset_mode):
            logger.info(f"Successfully tested and reset {camera_label}.")
            results[camera_label] = True
        else:
            logger.error(
                f"CRITICAL: Tested {camera_label} but failed to reset to '{reset_mode}'.",
            )
            results[camera_label] = False

    return results
