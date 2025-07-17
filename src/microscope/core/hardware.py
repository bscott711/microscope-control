"""
hardware.py

Hardware-specific functions for controlling ASI Tiger/PLogic devices.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Optional

from pymmcore_plus import CMMCorePlus

from .constants import HardwareConstants
from .settings import AcquisitionSettings

# Create a single instance of the hardware constants to be used as a default
hw_constants = HardwareConstants()

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)
logger.propagate = False


@contextmanager
def tiger_command_session(mmc: CMMCorePlus, hw: HardwareConstants) -> Iterator[None]:
    """
    A context manager to safely send a series of Tiger commands.

    This temporarily sets 'OnlySendSerialCommandOnChange' to 'No' to ensure
    all commands are sent, then restores the original setting.
    """
    hub_label = hw.tiger_comm_hub_label
    hub_prop = "OnlySendSerialCommandOnChange"
    original_setting = get_property(mmc, hub_label, hub_prop)
    try:
        if original_setting != "No":
            set_property(mmc, hub_label, hub_prop, "No")
        yield
    finally:
        # Check that we have a valid setting to restore before calling set_property
        if original_setting is not None and original_setting != "No":
            set_property(mmc, hub_label, hub_prop, original_setting)


def get_property(mmc: CMMCorePlus, device_label: str, property_name: str) -> Optional[str]:
    """Safely gets a Micro-Manager device property value."""
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        val = mmc.getProperty(device_label, property_name)
        logger.debug(f"Got {device_label}.{property_name} = {val}")
        return val
    logger.warning(f"Property '{property_name}' not found on '{device_label}'")
    return None


def set_property(mmc: CMMCorePlus, device_label: str, property_name: str, value: str) -> bool:
    """Sets a Micro-Manager device property only if it has changed."""
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
        return True


def send_tiger_command(mmc: CMMCorePlus, cmd: str) -> bool:
    """Sends a serial command to the TigerCommHub device."""
    if "TigerCommHub" not in mmc.getLoadedDevices():
        logger.error(f"TigerCommHub not loaded. Cannot send command: {cmd}")
        return False

    try:
        mmc.setProperty("TigerCommHub", "SerialCommand", cmd)
        logger.debug(f"Tiger command sent: {cmd}")
        # A small delay is often helpful for the controller to process commands
        time.sleep(0.01)
        return True
    except Exception as e:
        logger.error(f"Failed to send Tiger command: {cmd} - {e}", exc_info=True)
        return False


def query_tiger_command(mmc: CMMCorePlus, cmd: str) -> str:
    """Sends a serial query to the TigerCommHub and returns the response."""
    if "TigerCommHub" not in mmc.getLoadedDevices():
        logger.error(f"TigerCommHub not loaded. Cannot send query: {cmd}")
        return ""

    try:
        mmc.setProperty("TigerCommHub", "SerialCommand", cmd)
        time.sleep(0.01)
        response = mmc.getProperty("TigerCommHub", "SerialResponse")
        logger.debug(f"Tiger query '{cmd}' -> '{response}'")
        return response
    except Exception as e:
        logger.error(f"Failed to send Tiger query: {cmd} - {e}", exc_info=True)
        return ""


def open_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Configures and opens the global shutter on PLogic BNC3."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]

    logger.info("Opening global shutter (BNC3 HIGH)")
    with tiger_command_session(mmc, hw):
        # Program cell 12 to be a constant HIGH signal.
        send_tiger_command(mmc, f"M E={hw.plogic_always_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=0")  # Cell type: constant
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=1")  # Value: HIGH

        # Route the "always on" cell's output to BNC3.
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_always_on_cell}")

        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")


def close_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Closes the global shutter by routing BNC3 to GND (LOW)."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]

    logger.info("Closing global shutter (BNC3 LOW)")
    with tiger_command_session(mmc, hw):
        # Route BNC3 output to ground (address 0).
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=0")
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")


def configure_plogic_for_dual_nrt_pulses(
    mmc: CMMCorePlus, settings: AcquisitionSettings, hw: HardwareConstants = hw_constants
):
    """Configures PLogic for synchronized camera and laser triggers."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    logger.info("Configuring PLogic for hardware-timed acquisition.")

    with tiger_command_session(mmc, hw):
        # Step 1: Use the preset that was working for camera triggers.
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X={hw.plogic_laser_preset_num}")

        # --- Camera Pulse Configuration (Cell 11) ---
        camera_pulse_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={camera_pulse_cycles}")
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
        )

        # --- Laser Pulse Configuration (Cell 10) ---
        laser_pulse_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={laser_pulse_cycles}")
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
        )

        # --- Output Routing ---
        # Route Camera Trigger (Cell 11) to BNC1 (Address 33)
        send_tiger_command(mmc, "M E=33")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_camera_cell}")

        # Save configuration to the card
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")

    logger.info("PLogic configured for dual NRT pulses.")


def set_camera_trigger_mode_level_high(
    mmc: CMMCorePlus,
    hw: HardwareConstants = hw_constants,
    desired_modes=("Level Trigger", "Edge Trigger"),
) -> dict[str, bool]:
    """Sets the camera trigger mode to an external hardware mode for all specified cameras."""
    results = {}
    camera_labels = [hw.camera_a_label, hw.camera_b_label]

    for camera_label in camera_labels:
        if camera_label not in mmc.getLoadedDevices():
            logger.warning(f"Camera '{camera_label}' not loaded, skipping.")
            continue

        if not mmc.hasProperty(camera_label, "TriggerMode"):
            logger.warning(f"Camera '{camera_label}' does not support TriggerMode.")
            results[camera_label] = False
            continue

        allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
        success = False

        for mode in desired_modes:
            if mode in allowed:
                try:
                    set_property(mmc, camera_label, "TriggerMode", mode)
                    logger.info(f"Set {camera_label} trigger mode to '{mode}'.")
                    success = True
                    break
                except Exception as e:
                    logger.error(f"Failed to set {camera_label} to '{mode}': {e}")
        if not success:
            logger.warning(f"Could not set any of {desired_modes} for {camera_label}.")

        results[camera_label] = success

    return results


def reset_camera_trigger_mode_internal(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants) -> dict[str, bool]:
    """Sets the camera trigger mode to 'Internal Trigger' for all specified cameras."""
    results = {}
    camera_labels = [hw.camera_a_label, hw.camera_b_label]
    internal_mode = "Internal Trigger"

    for camera_label in camera_labels:
        if camera_label not in mmc.getLoadedDevices():
            logger.warning(f"Camera '{camera_label}' not loaded, skipping reset.")
            continue

        if not mmc.hasProperty(camera_label, "TriggerMode"):
            logger.warning(f"Camera '{camera_label}' does not support TriggerMode, skipping reset.")
            results[camera_label] = False
            continue

        allowed = mmc.getAllowedPropertyValues(camera_label, "TriggerMode")
        if internal_mode in allowed:
            try:
                set_property(mmc, camera_label, "TriggerMode", internal_mode)
                logger.debug(f"Reset {camera_label} trigger mode to '{internal_mode}'.")
                results[camera_label] = True
            except Exception as e:
                logger.error(f"Failed to reset {camera_label} to '{internal_mode}': {e}")
                results[camera_label] = False
        else:
            logger.warning(f"'{internal_mode}' is not a supported mode for {camera_label}.")
            results[camera_label] = False

    return results


def configure_galvo_for_hardware_timed_scan(
    mmc: CMMCorePlus,
    settings: AcquisitionSettings,
    hw: HardwareConstants = hw_constants,
):
    """
    Configure the galvo for a fully hardware-timed staircase scan (Z-stack).

    This function sends serial commands to the Tiger controller to configure
    a hardware-timed scan based on the MM_SPIM firmware module.
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for hardware-timed scan...")

    try:
        parts = galvo_label.split(":")
        address = parts[-1]
        axis_name = parts[1][0]
    except IndexError:
        logger.error(f"Could not parse address and axis from galvo label: {galvo_label}")
        return False

    if settings.num_slices > 1:
        total_range_um = (settings.num_slices - 1) * settings.step_size_um
        total_range_deg = total_range_um / hw.slice_calibration_slope_um_per_deg
    else:
        total_range_deg = 0.0

    pos_str = get_property(mmc, galvo_label, "SingleAxisXOffset(deg)")
    if pos_str is None:
        raise RuntimeError(f"Could not get current position for galvo '{galvo_label}'.")
    current_pos_deg = float(pos_str)
    center_pos_deg = current_pos_deg + (total_range_deg / 2.0)

    try:
        with tiger_command_session(mmc, hw):
            # Set scan center and amplitude
            send_tiger_command(mmc, f"{address}SAO {axis_name}={center_pos_deg:.4f}")
            send_tiger_command(mmc, f"{address}SAA {axis_name}={total_range_deg:.4f}")
            logger.debug(f"Galvo geometry set: Center={center_pos_deg:.4f} deg, Range={total_range_deg:.4f} deg")

            # Configure scan parameters (MM_SPIM)
            send_tiger_command(mmc, f"{address}SCANR Y={settings.num_slices} Z={hw.SPIM_MODE_BYTE}")
            send_tiger_command(
                mmc,
                f"{address}SCANV F={hw.SCAN_SETTLE_TIME_MS} T={hw.CAMERA_LASER_DELAY_MS} R={hw.CAMERA_LASER_DELAY_MS}",
            )
            exposure_ms = settings.camera_exposure_ms
            send_tiger_command(mmc, f"{address}RT T={exposure_ms} R={exposure_ms}")

        logger.info(
            "Galvo sequence configured for %d steps with %.2f um/slice.",
            settings.num_slices,
            settings.step_size_um,
        )
        return True

    except Exception as e:
        logger.error(f"Error configuring galvo for hardware scan: {e}", exc_info=True)
        return False


def enable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Sets PLogic to preset 12 for live/snap mode laser output."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X=12"
    logger.debug("Enabling laser for live/snap mode using preset 12.")
    return send_tiger_command(mmc, cmd)


def disable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Sets PLogic to preset 10 to disable laser output after live/snap."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X=10"
    logger.debug("Disabling laser for live/snap mode using preset 10.")
    return send_tiger_command(mmc, cmd)


def wake_piezo(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants) -> bool:
    """Sends a relative move of 0 to wake the piezo stage."""
    piezo_addr = hw.piezo_a_label.split(":")[-1]
    cmd = f"{piezo_addr}R P=0"
    logger.debug(f"Waking up piezo with command: {cmd}")
    return send_tiger_command(mmc, cmd)


def set_piezo_sleep(mmc: CMMCorePlus, hw: HardwareConstants, enabled: bool) -> bool:
    """Enables or disables piezo sleep mode."""
    piezo_addr = hw.piezo_a_label.split(":")[-1]
    # In firmware v3.11+, PZ F sets the auto-sleep timer.
    # A non-zero value enables sleep, 0 disables it.
    mode_val = 5 if enabled else 0  # 5 minutes for sleep, 0 to disable
    state_str = "Enabling" if enabled else "Disabling"
    cmd = f"{piezo_addr}PZ F={mode_val}"
    logger.info(f"{state_str} piezo sleep.")
    return send_tiger_command(mmc, cmd)
