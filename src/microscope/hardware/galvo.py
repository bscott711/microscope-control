# src/microscope/hardware/galvo.py
"""
galvo.py
Functions for configuring and controlling the ASI galvo scanner (SPIM controller).
This module handles all aspects of setting up the galvo for a hardware-timed SPIM
scan, including amplitude, timing, and triggering the acquisition.
"""

import logging

from pymmcore_plus import CMMCorePlus

from microscope.model.hardware_model import HardwareConstants

from .core import get_property, set_property

# Set up logger
logger = logging.getLogger(__name__)


def configure_galvo_for_spim_scan(
    mmc: CMMCorePlus,
    galvo_amplitude_deg: float,
    num_slices: int,
    num_repeats: int,
    repeat_delay_ms: float,
    hw: HardwareConstants,
) -> bool:
    """
    Configures the Galvo device for SPIM scanning by setting a block of properties.

    Args:
        mmc: The CMMCorePlus instance.
        galvo_amplitude_deg: The scanning amplitude in degrees.
        num_slices: The number of slices to scan in a volume.
        num_repeats: The number of times to repeat the volume scan (for time-series).
        repeat_delay_ms: The delay in milliseconds between volume repeats.
        hw: The hardware constants object.

    Returns:
        True if all configuration properties were set successfully, False otherwise.
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for SPIM scan...")

    # Define all parameters as a dictionary for clarity and easy modification.
    # The `set_property` helper handles converting values to strings.
    params = {
        "BeamEnabled": "Yes",
        "SPIMAlternateDirectionsEnable": "No",
        "SPIMInterleaveSidesEnable": "No",
        "SPIMPiezoHomeDisable": "No",
        "SPIMNumSides": 1,
        "SPIMFirstSide": "A",
        "SingleAxisXAmplitude(deg)": 0,
        "SingleAxisXOffset(deg)": 0,
        "SingleAxisYOffset(deg)": 0,
        "SPIMNumSlicesPerPiezo": hw.line_scans_per_slice,
        "SPIMDelayBeforeSide(ms)": hw.delay_before_side_ms,
        "SPIMScanDuration(ms)": hw.line_scan_duration_ms,
        "SPIMNumRepeats": num_repeats,
        "SPIMDelayBeforeRepeat(ms)": repeat_delay_ms,
        "SingleAxisYAmplitude(deg)": galvo_amplitude_deg,
        "SPIMNumSlices": num_slices,
    }

    # Atomically apply all properties; fail if any single one fails.
    for prop, value in params.items():
        if not set_property(mmc, galvo_label, prop, value):
            logger.error(
                f"Failed to configure {galvo_label}. Could not set property '{prop}' to '{value}'.",
            )
            return False

    logger.info(f"{galvo_label} configured successfully for SPIM scan.")
    return True


def trigger_spim_scan_acquisition(mmc: CMMCorePlus, hw: HardwareConstants) -> bool:
    """
    Triggers the SPIM scan acquisition and verifies the state change.

    Args:
        mmc: The CMMCorePlus instance.
        hw: The hardware constants object.

    Returns:
        True if the trigger was sent and the state was verified as 'Running'.
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Triggering SPIM scan acquisition on {galvo_label}...")

    if not set_property(mmc, galvo_label, "SPIMState", "Running"):
        logger.error(f"Failed to send 'Running' trigger to {galvo_label}.")
        return False

    # Verify that the state changed as expected
    spim_state = get_property(mmc, galvo_label, "SPIMState")
    if spim_state == "Running":
        logger.info(f"{galvo_label} state is now 'Running'.")
        return True

    logger.error(
        f"Sent trigger to {galvo_label}, but current state is '{spim_state}'.",
    )
    return False
