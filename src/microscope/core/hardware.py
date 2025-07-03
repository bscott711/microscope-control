"""
hardware.py

Hardware-specific functions for controlling ASI Tiger/PLogic devices.
"""

import logging
import time
from typing import Optional

from pymmcore_plus import CMMCorePlus

from .constants import HardwareConstants

# Create a single instance of the hardware constants to be used as a default
hw_constants = HardwareConstants()

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_property(mmc: CMMCorePlus, device_label: str, property_name: str) -> Optional[str]:
    """
    Safely gets a Micro-Manager device property value.

    Args:
        mmc: Core instance
        device_label: The label of the device in Micro-Manager.
        property_name: The name of the property to retrieve.

    Returns:
        The property value as a string if found, otherwise None.
    """
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        val = mmc.getProperty(device_label, property_name)
        logger.debug(f"Got {device_label}.{property_name} = {val}")
        return val
    logger.warning(f"Property '{property_name}' not found on '{device_label}'")
    return None


def set_property(mmc: CMMCorePlus, device_label: str, property_name: str, value: str) -> bool:
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


def send_tiger_command(mmc: CMMCorePlus, cmd: str) -> bool:
    """
    Sends a serial command to the TigerCommHub device.

    Args:
        mmc: Core instance
        cmd: Serial command to send.

    Returns:
        True if command was sent, False otherwise.
    """
    tiger_label = "TigerCommHub"

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


def open_global_shutter(mmc: CMMCorePlus, hw=hw_constants):
    """
    Configures and opens the global shutter on PLogic BNC3.
    This function programs a PLogic cell to be constantly high and routes it
    to the BNC3 output. This serves as a "microscope on" or global shutter signal.
    """
    plogic_label = hw.plogic_label
    plogic_addr_prefix = plogic_label.split(":")[-1]

    hub_label = hw.tiger_comm_hub_label
    hub_prop = "OnlySendSerialCommandOnChange"

    original_setting = get_property(mmc, hub_label, hub_prop)

    logger.info("Opening global shutter (BNC3 HIGH)")
    try:
        # Temporarily allow sending unchanged commands
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "No")

        # Clear previous settings
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X=0")

        # Program a PLogic cell to output a constant HIGH signal
        send_tiger_command(mmc, f"M E={hw.plogic_always_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=0")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=5")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCB X=1")

        # Route the "always on" cell's output to BNC3
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_always_on_cell}")

        # Save settings to card
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")

        logger.info("Global shutter is open (BNC3 is HIGH).")
    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "Yes")


def close_global_shutter(mmc: CMMCorePlus, hw=hw_constants):
    """
    Closes the global shutter by routing BNC3 to GND (LOW).
    """
    plogic_label = hw.plogic_label
    plogic_addr_prefix = plogic_label.split(":")[-1]
    hub_label = hw.tiger_comm_hub_label
    hub_prop = "OnlySendSerialCommandOnChange"

    original_setting = get_property(mmc, hub_label, hub_prop)

    logger.info("Closing global shutter (BNC3 LOW)")
    try:
        if plogic_label not in mmc.getLoadedDevices():
            logger.error("PLogic device not found, cannot close shutter.")
            return False

        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "No")

        # Route BNC3 output to GND
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=0")
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")

        logger.info("Global shutter is closed (BNC3 is LOW).")
    except Exception as e:
        logger.error(f"Could not close global shutter: {e}", exc_info=True)
    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, original_setting)
    return True


def configure_plogic_for_dual_nrt_pulses(mmc: CMMCorePlus, settings, hw=hw_constants):
    """
    Configures PLogic to generate two independent, synchronized NRT one-shot pulses
    for the camera and laser triggers.

    Args:
        mmc: Core instance
        settings: AcquisitionSettings object with exposure/laser timing info
        hw: HardwareConstants object containing hardware addresses and defaults

    Returns:
        True if successful, False otherwise
    """
    plogic_label = hw.plogic_label
    plogic_addr_prefix = plogic_label.split(":")[-1]
    hub_label = hw.tiger_comm_hub_label
    hub_prop = "OnlySendSerialCommandOnChange"

    original_setting = get_property(mmc, hub_label, hub_prop)

    logger.info("Configuring PLogic for dual NRT pulses")

    try:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "No")

        # Step 1: Program Laser Preset
        logger.debug(f"Setting Laser preset number: {hw.plogic_laser_preset_num}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X={hw.plogic_laser_preset_num}")

        # Step 2: Program Camera Pulse (NRT One-Shot #1)
        logger.debug(f"Programming Camera pulse (cell {hw.plogic_camera_cell})")
        camera_pulse_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={camera_pulse_cycles}")
        send_tiger_command(
            mmc, f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0"
        )

        # Step 3: Program Laser Pulse (NRT One-Shot #2)
        logger.debug(f"Programming Laser pulse (cell {hw.plogic_laser_on_cell})")
        laser_pulse_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={laser_pulse_cycles}")
        send_tiger_command(
            mmc, f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0"
        )

        # Step 4: Route Camera Trigger Cell Output to BNC1
        logger.debug("Routing Camera Trigger Cell Output to BNC1")
        send_tiger_command(mmc, "M E=33")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_camera_cell}")

        # Step 5: Save configuration
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")
        logger.info("PLogic configured for dual NRT pulses")
        return True
    except Exception as e:
        logger.error(f"Error configuring PLogic: {e}", exc_info=True)
        return False
    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, original_setting)


def set_camera_trigger_mode_level_high(
    mmc: CMMCorePlus, hw=hw_constants, desired_modes=("Level Trigger", "Edge Trigger")
):
    """
    Sets the camera trigger mode to 'Level Trigger' if supported.

    Args:
        mmc: Core instance
        hw: Hardware constants object
        desired_modes: List of acceptable trigger modes

    Returns:
        True if successfully set, False otherwise
    """
    camera_label = hw.camera_a_label
    if camera_label not in mmc.getLoadedDevices():
        logger.warning(f"Camera '{camera_label}' not loaded")
        return False

    if not mmc.hasProperty(camera_label, "TriggerMode"):
        logger.warning(f"Camera '{camera_label}' does not support TriggerMode")
        return False

    allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
    for mode in desired_modes:
        if mode in allowed:
            result = mmc.setProperty(camera_label, "TriggerMode", mode)  # noqa: F841
            logger.info(f"Set Camera TriggerMode to {mode}")
            return True
    logger.warning(f"None of {desired_modes} supported for TriggerMode")
    return False


def configure_galvo_for_spim_scan(mmc: CMMCorePlus, galvo_amplitude_deg: float, num_slices: int, hw=hw_constants):
    """
    Configures the Galvo device for SPIM scanning.

    Args:
        mmc: Core instance
        galvo_amplitude_deg: Amplitude in degrees
        num_slices: Number of slices to scan
        hw: Hardware constants object

    Returns:
        True if configuration succeeded
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for SPIM scan")
    try:
        set_property(mmc, galvo_label, "BeamEnabled", "Yes")
        set_property(mmc, galvo_label, "SPIMNumSlicesPerPiezo", str(hw.line_scans_per_slice))
        set_property(mmc, galvo_label, "SPIMDelayBeforeRepeat(ms)", str(hw.delay_before_scan_ms))
        set_property(mmc, galvo_label, "SPIMNumRepeats", "1")
        set_property(mmc, galvo_label, "SPIMDelayBeforeSide(ms)", str(hw.delay_before_side_ms))
        set_property(mmc, galvo_label, "SPIMAlternateDirectionsEnable", "No")
        set_property(mmc, galvo_label, "SPIMScanDuration(ms)", str(hw.line_scan_duration_ms))
        set_property(mmc, galvo_label, "SingleAxisYAmplitude(deg)", str(galvo_amplitude_deg))
        set_property(mmc, galvo_label, "SingleAxisYOffset(deg)", "0")
        set_property(mmc, galvo_label, "SPIMNumSlices", str(num_slices))
        set_property(mmc, galvo_label, "SPIMNumSides", "1")
        set_property(mmc, galvo_label, "SPIMFirstSide", "A")
        set_property(mmc, galvo_label, "SPIMPiezoHomeDisable", "No")
        set_property(mmc, galvo_label, "SPIMInterleaveSidesEnable", "No")
        set_property(mmc, galvo_label, "SingleAxisXAmplitude(deg)", "0")
        set_property(mmc, galvo_label, "SingleAxisXOffset(deg)", "0")
        logger.info("Galvo configured for SPIM scan")
        return True
    except Exception as e:
        logger.error(f"Error configuring galvo: {e}", exc_info=True)
        return False


def trigger_spim_scan_acquisition(mmc: CMMCorePlus, galvo_label: str = hw_constants.galvo_a_label):
    """
    Triggers the SPIM scan acquisition by setting SPIMState to Running.
    """
    logger.info("Triggering SPIM scan acquisition...")
    try:
        set_property(mmc, galvo_label, "SPIMState", "Running")
        spim_state = get_property(mmc, galvo_label, "SPIMState")
        logger.debug(f"{galvo_label} SPIMState: {spim_state}")
        return True
    except Exception as e:
        logger.error(f"Failed to start SPIM scan: {e}", exc_info=True)
        return False


def reset_for_next_volume(mmc: CMMCorePlus, galvo_label: str = hw_constants.galvo_a_label):
    """
    Resets scanner state after volume acquisition.
    """
    logger.info("Resetting controller state for next volume...")
    set_property(mmc, galvo_label, "SPIMState", "Idle")
