# src/microscope/core/hardware/plogic.py

"""
Functions for controlling and programming the ASI PLogic card.
"""

import logging

from pymmcore_plus import CMMCorePlus

from .. import AcquisitionSettings, HardwareConstants
from .utils import get_property, send_tiger_command, set_property

logger = logging.getLogger(__name__)


def open_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants):
    """Configures and opens the global shutter on PLogic BNC3."""
    plogic_addr = hw.plogic_label.split(":")[-1]
    original_setting = get_property(mmc, hw.tiger_comm_hub_label, "OnlySendSerialCommandOnChange")

    logger.info("Opening global shutter (BNC3 HIGH)")
    try:
        if original_setting == "Yes":
            set_property(mmc, hw.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "No")

        send_tiger_command(mmc, f"M E={hw.plogic_always_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr}CCA Y=0 Z=5")
        send_tiger_command(mmc, f"{plogic_addr}CCB X=1")
        send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
        send_tiger_command(mmc, f"{plogic_addr}CCA Z={hw.plogic_always_on_cell}")
        send_tiger_command(mmc, f"{plogic_addr}SS Z")
    finally:
        if original_setting == "Yes":
            set_property(mmc, hw.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "Yes")


def close_global_shutter(mmc: CMMCorePlus, hw: HardwareConstants):
    """Closes the global shutter by routing BNC3 to GND (LOW)."""
    plogic_addr = hw.plogic_label.split(":")[-1]
    send_tiger_command(mmc, f"M E={hw.plogic_bnc3_addr}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Z=0")
    send_tiger_command(mmc, f"{plogic_addr}SS Z")
    logger.info("Global shutter is closed (BNC3 is LOW).")


def configure_plogic_for_dual_nrt_pulses(mmc: CMMCorePlus, settings: AcquisitionSettings, hw: HardwareConstants):
    """Configures PLogic to generate synchronized pulses for camera and laser."""
    plogic_addr = hw.plogic_label.split(":")[-1]

    # Program Laser Preset
    send_tiger_command(mmc, f"{plogic_addr}CCA X={hw.plogic_laser_preset_num}")

    # Program Camera Pulse
    cam_cycles = int(settings.camera_exposure_ms * hw.pulses_per_ms)
    send_tiger_command(mmc, f"M E={hw.plogic_camera_cell}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Y=14 Z={cam_cycles}")
    send_tiger_command(mmc, f"{plogic_addr}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0")

    # Program Laser Pulse
    laser_cycles = int(settings.laser_trig_duration_ms * hw.pulses_per_ms)
    send_tiger_command(mmc, f"M E={hw.plogic_laser_on_cell}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Y=14 Z={laser_cycles}")
    send_tiger_command(mmc, f"{plogic_addr}CCB X={hw.plogic_trigger_ttl_addr} Y={hw.plogic_4khz_clock_addr} Z=0")

    # Route Camera Trigger to BNC1
    send_tiger_command(mmc, "M E=33")
    send_tiger_command(mmc, f"{plogic_addr}CCA Z={hw.plogic_camera_cell}")

    # Save configuration
    send_tiger_command(mmc, f"{plogic_addr}SS Z")
    logger.info("PLogic configured for dual NRT pulses.")


def enable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants):
    """Sets PLogic to preset 12 for live/snap mode laser output."""
    plogic_addr = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr}CCA X=12"
    logger.info("Enabling laser for live/snap mode.")
    send_tiger_command(mmc, cmd)


def disable_live_laser(mmc: CMMCorePlus, hw: HardwareConstants):
    """Sets PLogic to preset 10 to disable laser output after live/snap."""
    plogic_addr = hw.plogic_label.split(":")[-1]
    cmd = f"{plogic_addr}CCA X=10"
    logger.info("Disabling laser for live/snap mode.")
    send_tiger_command(mmc, cmd)
