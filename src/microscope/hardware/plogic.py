# src/microscope/hardware/plogic.py
"""
plogic.py
Functions for configuring and controlling the ASI PLogic card.
This module handles programming the PLogic's logic cells, setting presets,
and managing the global shutter and laser triggers.
"""

import logging

from pymmcore_plus import CMMCorePlus

from microscope.model.hardware_model import AcquisitionSettings, HardwareConstants

from .core import get_property, send_tiger_command, set_property

# Set up logger
logger = logging.getLogger(__name__)


def open_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
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
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X=0", hw)

        # Program a PLogic cell to output a constant HIGH signal
        send_tiger_command(mmc, f"M E={hw.plogic_always_on_cell}", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=0", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=5", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCB X=1", hw)

        # Route the "always on" cell's output to BNC3
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_always_on_cell}", hw)

        # Save settings to card
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z", hw)
        logger.info("Global shutter is open (BNC3 is HIGH).")
        return True

    except Exception as e:
        logger.error(f"Failed to open global shutter: {e}", exc_info=True)
        return False

    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, original_setting)


def close_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
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
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z=0", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z", hw)
        logger.info("Global shutter is closed (BNC3 is LOW).")
        return True

    except Exception as e:
        logger.error(f"Could not close global shutter: {e}", exc_info=True)
        return False

    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, original_setting)


def configure_plogic_for_dual_nrt_pulses(
    mmc: CMMCorePlus, settings: AcquisitionSettings, hw: HardwareConstants
) -> bool:
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
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA X={hw.plogic_laser_preset_num}", hw)

        # Step 2: Program Camera Pulse (NRT One-Shot #1)
        logger.debug(f"Programming Camera pulse (cell {hw.plogic_camera_cell})")
        camera_pulse_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={camera_pulse_cycles}", hw)
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
            hw,
        )

        # Step 3: Program Laser Pulse (NRT One-Shot #2)
        logger.debug(f"Programming Laser pulse (cell {hw.plogic_laser_on_cell})")
        laser_pulse_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)
        send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Y=14", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={laser_pulse_cycles}", hw)
        send_tiger_command(
            mmc,
            f"{plogic_addr_prefix}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0",
            hw,
        )

        # Step 4: Route Camera Trigger Cell Output to BNC1
        logger.debug("Routing Camera Trigger Cell Output to BNC1")
        send_tiger_command(mmc, "M E=33", hw)
        send_tiger_command(mmc, f"{plogic_addr_prefix}CCA Z={hw.plogic_camera_cell}", hw)

        # Step 5: Save configuration
        send_tiger_command(mmc, f"{plogic_addr_prefix}SS Z", hw)
        logger.info("PLogic configured for dual NRT pulses")
        return True

    except Exception as e:
        logger.error(f"Error configuring PLogic: {e}", exc_info=True)
        return False

    finally:
        if original_setting == "Yes":
            set_property(mmc, hub_label, hub_prop, original_setting)


def enable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Sets PLogic to the live/snap mode laser preset.
    """
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X={hw.plogic_live_mode_preset}"
    logger.info("Enabling laser for live/snap mode.")
    return send_tiger_command(mmc, cmd, hw)


def disable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Sets PLogic to the idle mode laser preset after live/snap.
    """
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X={hw.plogic_idle_mode_preset}"
    logger.info("Disabling laser for live/snap mode.")
    return send_tiger_command(mmc, cmd, hw)
