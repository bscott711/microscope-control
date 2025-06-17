# src/microscope/config.py
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Optional

# --- Demo Mode Check ---
USE_DEMO_CONFIG = os.environ.get("MICROSCOPE_DEMO") in ("1", "true", "True")


# --- Core Data Structures ---
# These are now the primary data models for acquisition settings.


@dataclass
class Channel:
    """A single channel configuration for an acquisition."""

    name: str
    exposure_ms: float


@dataclass
class ZStack:
    """A single Z-stack configuration for an acquisition."""

    start_um: float
    end_um: float
    step_um: float

    @property
    def num_slices(self) -> int:
        """Derived number of slices in the Z-stack."""
        if self.step_um == 0:
            return 1
        return int(round(abs(self.end_um - self.start_um) / self.step_um)) + 1


@dataclass
class AcquisitionSettings:
    """
    Stores all user-configurable acquisition parameters.
    This dataclass is the single source of truth for an experiment's settings.
    """

    # Core sequence settings
    channels: Sequence[Channel] = field(default_factory=list)
    z_stack: Optional[ZStack] = None
    time_points: int = 1
    time_interval_s: float = 0.0

    # Data saving settings
    should_save: bool = False
    save_dir: str = ""
    save_prefix: str = "acquisition"

    # Hardware timing parameters derived from the core settings
    @property
    def camera_exposure_ms(self) -> float:
        """Derived camera exposure time."""
        # This could be more complex, e.g., finding max exposure in channels
        if self.channels:
            return self.channels[0].exposure_ms + 1.95
        return 10.0  # Default exposure if no channels are set

    @property
    def num_slices(self) -> int:
        """Derived number of slices."""
        return self.z_stack.num_slices if self.z_stack else 1


@dataclass
class HardwareConstants:
    """Stores fixed hardware configuration and constants."""

    cfg_path: str = "" if USE_DEMO_CONFIG else "hardware_profiles/20250523-OPM.cfg"

    # Device labels
    galvo_a_label: str = "Scanner:AB:33"
    piezo_a_label: str = "PiezoStage:P:34"
    camera_a_label: str = "Camera-1"
    plogic_label: str = "PLogic:E:36"
    tiger_comm_hub_label: str = "TigerCommHub"

    # PLogic addresses and presets
    plogic_camera_trigger_ttl_addr: int = 44
    plogic_laser_trigger_ttl_addr: int = 45
    plogic_galvo_trigger_ttl_addr: int = 43
    plogic_4khz_clock_addr: int = 192
    plogic_laser_on_cell: int = 10
    plogic_laser_preset_num: int = 5
    plogic_delay_before_laser_cell: int = 11
    plogic_delay_before_camera_cell: int = 12
    pulses_per_ms: float = 4.0

    # Calibration
    slice_calibration_slope_um_per_deg: float = 100.0
    slice_calibration_offset_um: float = 0.0

    # Timing Parameters
    delay_before_scan_ms: float = 0.0
    line_scans_per_slice: int = 1
    line_scan_duration_ms: float = 1.0
    num_sides: int = 1
    first_side_is_a: bool = True
    scan_opposite_directions: bool = False
    sheet_width_deg: float = 0.5
    sheet_offset_deg: float = 0.0
    delay_before_side_ms: float = 0.0
    camera_mode_is_overlap: bool = False


# Instantiate constants with the corrected name for consistency
hw_constants = HardwareConstants()

if USE_DEMO_CONFIG:
    print("...RUNNING IN DEMO MODE...")
