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

    If 'Multi Camera' is provided, it configures all physical cameras assigned to it.

    Args:
        mmc: The CMMCorePlus instance.
        camera_label: Label of the camera to configure (can be 'Multi Camera').
        preferred_modes: An ordered tuple of trigger modes to try.

    Returns:
        True if a suitable mode was successfully set for all cameras, False otherwise.
    """
    logger.info(f"Configuring '{camera_label}' for hardware-timed acquisition.")

    cameras_to_configure = []
    if mmc.getDeviceLibrary(camera_label) == "Utilities":
        num_channels = mmc.getNumberOfCameraChannels()
        cameras_to_configure = [mmc.getCameraChannelName(i) for i in range(num_channels)]
        logger.info(f"Multi Camera device detected. Configuring: {cameras_to_configure}")
    else:
        cameras_to_configure = [camera_label]

    all_successful = True
    for cam in cameras_to_configure:
        was_set = False
        for mode in preferred_modes:
            if _set_camera_trigger_mode(mmc, cam, mode):
                was_set = True
                break
        if not was_set:
            logger.error(f"Could not set a suitable trigger mode for {cam} from {preferred_modes}.")
            all_successful = False

    return all_successful


def reset_cameras_to_internal(mmc: CMMCorePlus, camera_label: str) -> None:
    """
    Resets the trigger mode of the specified camera(s) to 'Internal Trigger'.

    If 'Multi Camera' is provided, it resets all physical cameras assigned to it.

    Args:
        mmc: The CMMCorePlus instance.
        camera_label: The device label of the camera(s) to reset.
    """
    cameras_to_reset = []
    if mmc.getDeviceLibrary(camera_label) == "Utilities":
        num_channels = mmc.getNumberOfCameraChannels()
        cameras_to_reset = [mmc.getCameraChannelName(i) for i in range(num_channels)]
    else:
        cameras_to_reset = [camera_label]

    for cam in cameras_to_reset:
        if not _set_camera_trigger_mode(mmc, cam, "Internal Trigger"):
            logger.error(f"Failed to reset camera '{cam}' to 'Internal Trigger'.")
        else:
            logger.info(f"Camera {cam} reverted to Internal Trigger.")


def check_and_reset_camera_trigger_modes(
    mmc: CMMCorePlus,
    hw: HardwareConstants,
    external_modes: tuple[str, ...] = ("Level Trigger", "Edge Trigger"),
    reset_mode: str = "Internal Trigger",
) -> dict[str, bool]:
    """
    Verifies cameras can use an external trigger, then reverts to a safe state.

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
        was_set = False
        for mode in external_modes:
            if _set_camera_trigger_mode(mmc, camera_label, mode):
                was_set = True
                break

        if not was_set:
            logger.warning(f"Test failed: Could not set any of {external_modes} for {camera_label}.")
            results[camera_label] = False
            continue

        if _set_camera_trigger_mode(mmc, camera_label, reset_mode):
            logger.info(f"Successfully tested and reset {camera_label}.")
            results[camera_label] = True
        else:
            logger.error(
                f"CRITICAL: Tested {camera_label} but failed to reset to '{reset_mode}'.",
            )
            results[camera_label] = False

    return results
