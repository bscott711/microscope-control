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

from .core import set_property

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
    Configures the Galvo device for SPIM scanning.
    Args:
        mmc: Core instance
        galvo_amplitude_deg: Amplitude in degrees
        num_slices: Number of slices to scan
        num_repeats: Number of times to repeat the volume scan (for time-series).
        repeat_delay_ms: Delay in ms between volume repeats.
        hw: Hardware constants object
    Returns:
        True if configuration succeeded
    """
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for SPIM scan")
    try:
        # Enable the beam
        set_property(mmc, galvo_label, "BeamEnabled", "Yes")

        # Set SPIM parameters
        set_property(mmc, galvo_label, "SPIMNumSlicesPerPiezo", str(hw.line_scans_per_slice))
        set_property(mmc, galvo_label, "SPIMDelayBeforeRepeat(ms)", str(repeat_delay_ms))
        set_property(mmc, galvo_label, "SPIMNumRepeats", str(num_repeats))
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


def trigger_spim_scan_acquisition(mmc: CMMCorePlus, galvo_label: str, hw: HardwareConstants) -> bool:
    """
    Triggers the SPIM scan acquisition by setting SPIMState to Running.
    Args:
        mmc: Core instance
        galvo_label: Label of the galvo device
        hw: Hardware constants object (unused here but included for consistency)
    Returns:
        True if trigger was sent successfully
    """
    logger.info("Triggering SPIM scan acquisition...")
    try:
        set_property(mmc, galvo_label, "SPIMState", "Running")
        # Verify the state was set
        spim_state = mmc.getProperty(galvo_label, "SPIMState")
        logger.debug(f"{galvo_label} SPIMState: {spim_state}")
        return True
    except Exception as e:
        logger.error(f"Failed to start SPIM scan: {e}", exc_info=True)
        return False
