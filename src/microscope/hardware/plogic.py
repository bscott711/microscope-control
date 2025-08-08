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

from .core import send_tiger_command, tiger_command_batch

# Set up logger
logger = logging.getLogger(__name__)


def open_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Opens the global shutter by programming a PLogic cell to be constantly HIGH.
    """
    logger.debug("Opening global shutter (BNC3 HIGH)...")
    plogic_addr = hw.plogic_label.split(":")[-1]
    commands = [
        f"{plogic_addr}CCA X=0",  # Clear previous settings
        f"M E={hw.plogic_always_on_cell}",  # Address the "always on" cell
        f"{plogic_addr}CCA Y=0 Z=5",  # Program cell as constant HIGH
        f"{plogic_addr}CCB X=1",
        f"M E={hw.plogic_bnc3_addr}",  # Address BNC3 output
        f"{plogic_addr}CCA Z={hw.plogic_always_on_cell}",  # Route "always on" to BNC3
        f"{plogic_addr}SS Z",  # Save settings to card
    ]

    with tiger_command_batch(mmc, hw):
        for cmd in commands:
            if not send_tiger_command(mmc, cmd, hw):
                logger.error(f"Failed to send command to open shutter: {cmd}")
                return False

    logger.info("Global shutter is open (BNC3 is HIGH).")
    return True


def close_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Closes the global shutter by routing its output BNC to ground (LOW).
    """
    logger.debug("Closing global shutter (BNC3 LOW)...")
    if hw.plogic_label not in mmc.getLoadedDevices():
        logger.error("PLogic device not found, cannot close shutter.")
        return False

    plogic_addr = hw.plogic_label.split(":")[-1]
    commands = [
        f"M E={hw.plogic_bnc3_addr}",  # Address BNC3 output
        f"{plogic_addr}CCA Z=0",  # Route output to GND
        f"{plogic_addr}SS Z",  # Save settings
    ]

    with tiger_command_batch(mmc, hw):
        for cmd in commands:
            if not send_tiger_command(mmc, cmd, hw):
                logger.error(f"Failed to send command to close shutter: {cmd}")
                return False

    logger.info("Global shutter is closed (BNC3 is LOW).")
    return True


def configure_plogic_for_dual_nrt_pulses(
    mmc: CMMCorePlus, settings: AcquisitionSettings, hw: HardwareConstants
) -> bool:
    """
    Configures PLogic to generate two synchronized pulses for camera and laser.
    """
    logger.info("Configuring PLogic for dual NRT pulses...")
    plogic_addr = hw.plogic_label.split(":")[-1]
    routing_str = f"{plogic_addr}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0"
    cam_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
    laser_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)

    with tiger_command_batch(mmc, hw):
        commands_ok = (
            send_tiger_command(mmc, f"{plogic_addr}CCA X={hw.plogic_laser_preset_num}", hw)
            and send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}", hw)
            and send_tiger_command(mmc, f"{plogic_addr}CCA Y=14 Z={cam_cycles}", hw)
            and send_tiger_command(mmc, routing_str, hw)
            and send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}", hw)
            and send_tiger_command(mmc, f"{plogic_addr}CCA Y=14 Z={laser_cycles}", hw)
            and send_tiger_command(mmc, routing_str, hw)
            and send_tiger_command(mmc, f"M E={hw.plogic_bnc1_addr}", hw)
            and send_tiger_command(mmc, f"{plogic_addr}CCA Z={hw.plogic_camera_cell}", hw)
            and send_tiger_command(mmc, f"{plogic_addr}SS Z", hw)
        )
        if not commands_ok:
            logger.error("A command failed during PLogic configuration.")
            return False

    logger.info("PLogic configured successfully for dual NRT pulses.")
    return True


def enable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Sets PLogic to the live/snap mode laser preset.
    """
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X={hw.plogic_live_mode_preset}"
    logger.debug("Enabling laser for live/snap mode")
    return send_tiger_command(mmc, cmd, hw)


def disable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Sets PLogic to the idle mode laser preset after live/snap.
    """
    plogic_addr_prefix = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr_prefix}CCA X={hw.plogic_idle_mode_preset}"
    logger.debug("Disabling laser for live/snap mode.")
    return send_tiger_command(mmc, cmd, hw)
