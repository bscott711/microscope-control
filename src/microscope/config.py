# src/microscope/config.py
import os
from dataclasses import dataclass
from enum import Enum  # <--- Added import

# --- Demo Mode Check ---
USE_DEMO_CONFIG = os.environ.get("MICROSCOPE_DEMO") in ("1", "true", "True")


# --- Added Enum for Trigger Modes ---
class TriggerMode(str, Enum):
    """
    Camera trigger modes.
    The string values must match the values expected by the camera's driver.
    """

    INTERNAL = "Internal Trigger"
    EDGE = "Edge Trigger"
    LEVEL = "Level Trigger"
    LEVEL_OVERLAP = "Level Trigger Overlap"
    TRIGGER_FIRST = "Trigger First"
    SOFTWARE_EDGE = "Software Trigger Edge"
    SOFTWARE_FIRST = "Software Trigger First"


@dataclass
class AcquisitionSettings:
    """
    Stores all user-configurable acquisition parameters.
    This dataclass now includes all settings from the GUI to ensure type consistency.
    """

    # Hardware-related settings
    num_slices: int = 3
    step_size_um: float = 1.0
    piezo_center_um: float = -31.0
    laser_trig_duration_ms: float = 10.0
    delay_before_camera_ms: float = 18.0
    trigger_mode: TriggerMode = TriggerMode.EDGE  # <--- Added trigger_mode setting

    # Sequence and timing settings from the GUI
    time_points: int = 1
    time_interval_s: float = 0.0
    is_minimal_interval: bool = True

    # Data saving settings from the GUI
    should_save: bool = False
    save_dir: str = ""
    save_prefix: str = "acquisition"

    @property
    def camera_exposure_ms(self) -> float:
        """Derived camera exposure time."""
        return self.laser_trig_duration_ms + 1.95

    @property
    def delay_before_laser_ms(self) -> float:
        """Derived laser delay time."""
        return self.delay_before_camera_ms + 1.25


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


# Instantiate constants
HW = HardwareConstants()
if USE_DEMO_CONFIG:
    print("...RUNNING IN DEMO MODE...")
