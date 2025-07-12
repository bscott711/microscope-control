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
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "No")
        yield
    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, "Yes")


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
        return True  # Return True as the state is correct


def send_tiger_command(mmc: CMMCorePlus, cmd: str) -> bool:
    """Sends a serial command to the TigerCommHub device."""
    if "TigerCommHub" not in mmc.getLoadedDevices():
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


def open_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Configures and opens the global shutter on PLogic BNC3."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]

    logger.info("Opening global shutter (BNC3 HIGH)")
    with tiger_command_session(mmc, hw):
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


def close_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Closes the global shutter by routing BNC3 to GND (LOW)."""
    plogic_label = hw.plogic_label
    plogic_addr_prefix = plogic_label.split(":")[-1]

    logger.info("Closing global shutter (BNC3 LOW)")
    if plogic_label not in mmc.getLoadedDevices():
        logger.error("PLogic device not found, cannot close shutter.")
        return

    with tiger_command_session(mmc, hw):
        # Route BNC3 output to GND
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=0")
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")

    logger.info("Global shutter is closed (BNC3 is LOW).")


def configure_plogic_for_dual_nrt_pulses(
    mmc: CMMCorePlus, settings: AcquisitionSettings, hw: HardwareConstants = hw_constants
):
    """Configures PLogic for synchronized camera and laser triggers."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]

    logger.info("Configuring PLogic for dual NRT pulses")
    with tiger_command_session(mmc, hw):
        # Step 1: Program Laser Preset
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X={hw.plogic_laser_preset_num}")

        # Step 2: Program Camera Pulse
        camera_pulse_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={camera_pulse_cycles}")
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
        )

        # Step 3: Program Laser Pulse
        laser_pulse_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={laser_pulse_cycles}")
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
        )

        # Step 4: Route Camera Trigger Cell Output to BNC1
        send_tiger_command(mmc, "M E=33")
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_camera_cell}")

        # Step 5: Save configuration
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z")
    logger.info("PLogic configured for dual NRT pulses")


def set_camera_trigger_mode_level_high(
    mmc: CMMCorePlus,
    hw: HardwareConstants = hw_constants,
    desired_modes=("Level Trigger", "Edge Trigger"),
) -> dict[str, bool]:
    """Sets the camera trigger mode for all specified cameras."""
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
                    mmc.setProperty(camera_label, "TriggerMode", mode)
                    success = True
                    break
                except Exception as e:
                    logger.error(f"Failed to set {camera_label} to '{mode}': {e}")

        if not success:
            logger.warning(f"None of {desired_modes} found for {camera_label}.")
            results[camera_label] = False
            continue

        internal_mode = "Internal Trigger"
        if internal_mode in allowed:
            try:
                mmc.setProperty(camera_label, "TriggerMode", internal_mode)
                results[camera_label] = True
            except Exception as e:
                logger.error(f"Failed to revert {camera_label} to '{internal_mode}': {e}")
                results[camera_label] = False
        else:
            logger.warning(f"'{internal_mode}' is not supported for {camera_label}.")
            results[camera_label] = False

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

    This function implements the documented procedure for using the ASI Tiger
    controller's `MM_SPIM` firmware to generate a galvo-triggered Z-stack.
    The process is a two-part configuration:

    1.  **Physical Geometry (`singleaxis` commands):**
        We define the absolute physical space of the scan.
        - `SAO` (Single-Axis Offset): Sets the absolute center of the scan range.
        - `SAA` (Single-Axis Amplitude): Sets the total peak-to-peak travel
          distance of the scan.

    2.  **Digital Sequence & Timing (`MM_SPIM` commands):**
        We define the discrete steps and triggers within that physical space.
        - `SCANR Y`: Sets the number of discrete slices (steps).
        - `SCANR Z`: A mode byte to control hardware behavior. We set bit 3
          to disable the "return-to-home" action after each step, which is
          essential for the staircase to progress.
        - `SCANV F`: Sets the "settle time" to wait after the galvo moves
          to a new position before any triggers are fired.
        - `SCANV T/R`: Sets the delay from the end of the settle time to when
          the camera and laser triggers are sent.
        - `RT T/R`: Sets the duration of the level trigger pulse for the
          camera and laser.

    After this function runs, the galvo is fully armed. A single `SCAN`
    command will then initiate the entire autonomous, hardware-timed sequence.

    Args:
        mmc: The CMMCorePlus instance.
        settings: An AcquisitionSettings object containing parameters like
                  number of slices and step size.
        hw: The HardwareConstants object.

    Returns:
        True if configuration was successful, False otherwise.
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for hardware-timed scan...")

    # 1. DEFINE PHYSICAL SCAN GEOMETRY
    if settings.num_slices > 1:
        total_range_um = (settings.num_slices - 1) * settings.step_size_um
        total_range_deg = total_range_um / hw.slice_calibration_slope_um_per_deg
    else:
        total_range_deg = 0.0

    pos_str = get_property(mmc, galvo_label, "Position")
    if pos_str is None:
        raise RuntimeError(f"Could not get current position for galvo '{galvo_label}'.")
    current_pos_deg = float(pos_str)
    center_pos_deg = current_pos_deg + (total_range_deg / 2.0)

    try:
        # Set the center position (offset) of the scan
        set_property(mmc, galvo_label, "SAO", str(center_pos_deg))
        # Set the total peak-to-peak travel distance (amplitude)
        set_property(mmc, galvo_label, "SAA", str(total_range_deg))
        logger.debug(
            f"Galvo geometry set: Center={center_pos_deg:.4f} deg, "
            f"Range={total_range_deg:.4f} deg"
        )

        # 2. DEFINE DIGITAL SEQUENCE & TIMING (MM_SPIM Syntax)
        set_property(mmc, galvo_label, "SCANR Y", str(settings.num_slices))
        set_property(mmc, galvo_label, "SCANR Z", str(hw.SPIM_MODE_BYTE))
        set_property(mmc, galvo_label, "SCANV F", str(hw.SCAN_SETTLE_TIME_MS))
        set_property(mmc, galvo_label, "SCANV T", str(hw.CAMERA_LASER_DELAY_MS))
        set_property(mmc, galvo_label, "SCANV R", str(hw.CAMERA_LASER_DELAY_MS))

        exposure_ms = settings.camera_exposure_ms
        set_property(mmc, galvo_label, "RT T", str(exposure_ms))
        set_property(mmc, galvo_label, "RT R", str(exposure_ms))

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
    logger.debug("Enabling laser for live/snap mode.")
    return send_tiger_command(mmc, cmd)


def disable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants = hw_constants):
    """Sets PLogic to preset 10 to disable laser output after live/snap."""
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X=10"
    logger.debug("Disabling laser for live/snap mode.")
    return send_tiger_command(mmc, cmd)


def format_device_response(response_text: str) -> str:
    """Parses the raw device response into a human-readable format."""
    cleaned_response = response_text.replace("\\r", "\n")
    lines = [line.strip() for line in cleaned_response.splitlines() if line.strip()]

    if len(lines) == 1:
        line = lines[0]
        is_complex = any(k in line for k in ["Axis", "Addr", "BootLdr", "Hdwr"])
        if not is_complex:
            return line

    parts = {"Axis": [], "System": [], "Features": []}
    for line in lines:
        if "axis" in line.lower() or "addr" in line.lower():
            parts["Axis"].append(line)
        elif any(k in line for k in ["BootLdr", "Hdwr", "CMDS", "RING", "SAVED"]):
            parts["System"].append(line)
        else:
            parts["Features"].append(line)

    output = ["--- Device Configuration & Status ---"]
    if parts["Axis"]:
        output.append("\n## Axis Information")
        output.extend(f"- {item}" for item in parts["Axis"])
    if parts["System"]:
        output.append("\n## System Information")
        output.extend(f"- {item}" for item in parts["System"])
    if parts["Features"]:
        output.append("\n## Supported Features & Modules ⚙️")
        output.extend(f"- {item}" for item in parts["Features"])

    return "\n".join(output) if len(output) > 1 else response_text


def send_and_print_command(mmc: CMMCorePlus, command: str):
    """Sends a command, gets the raw response, formats it, and prints it."""
    print(f"▶️ Sending Command: '{command}'")
    mmc.setProperty("TigerCommHub", "SerialCommand", command)
    raw_response = mmc.getProperty("TigerCommHub", "SerialResponse")
    print(format_device_response(raw_response))
