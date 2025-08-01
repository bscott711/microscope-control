# src/microscope/core/hardware/galvo.py

"""
Functions for configuring and controlling the ASI Galvo scanner for SPIM.
"""

import logging

from pymmcore_plus import CMMCorePlus

from ..constants import HardwareConstants
from .utils import set_property

logger = logging.getLogger(__name__)


def configure_galvo_for_spim_scan(
    mmc: CMMCorePlus,
    galvo_amplitude_deg: float,
    num_slices: int,
    num_repeats: int,
    repeat_delay_ms: float,
    hw: HardwareConstants,
):
    """Configures the Galvo device for a hardware-timed SPIM scan."""
    galvo_label = hw.galvo_a_label
    logger.info(f"Configuring {galvo_label} for SPIM scan.")

    set_property(mmc, galvo_label, "BeamEnabled", "Yes")
    set_property(mmc, galvo_label, "SPIMNumSlicesPerPiezo", str(hw.line_scans_per_slice))
    set_property(mmc, galvo_label, "SPIMDelayBeforeRepeat(ms)", str(repeat_delay_ms))
    set_property(mmc, galvo_label, "SPIMNumRepeats", str(num_repeats))
    set_property(mmc, galvo_label, "SPIMDelayBeforeSide(ms)", str(hw.delay_before_side_ms))
    set_property(mmc, galvo_label, "SPIMScanDuration(ms)", str(hw.line_scan_duration_ms))
    set_property(mmc, galvo_label, "SingleAxisYAmplitude(deg)", str(galvo_amplitude_deg))
    set_property(mmc, galvo_label, "SPIMNumSlices", str(num_slices))
    set_property(mmc, galvo_label, "SPIMNumSides", "1")

    logger.info("Galvo configured for SPIM scan.")


def trigger_spim_scan_acquisition(mmc: CMMCorePlus, galvo_label: str):
    """Triggers the SPIM scan by setting SPIMState to Running."""
    logger.info("Triggering SPIM scan acquisition...")
    set_property(mmc, galvo_label, "SPIMState", "Running")
