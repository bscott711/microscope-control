# microscope/config.py
import os
from dataclasses import dataclass

# --- Demo Mode Check ---
USE_DEMO_CONFIG = os.environ.get("MICROSCOPE_DEMO") in ("1", "true", "True")


@dataclass
class AcquisitionSettings:
    """Stores all user-configurable acquisition parameters."""

    num_slices: int = 3
    step_size_um: float = 1.0
    piezo_center_um: float = -31.0
    laser_trig_duration_ms: float = 10.0
    delay_before_camera_ms: float = 18.0

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

    # --- PLogic Addresses (corrected from user feedback) ---
    # Physical TTL lines
    camera_trigger_addr: int = 41  # TTL Output 0
    laser_trigger_addr: int = 42  # TTL Output 1
    side_select_addr: int = 44  # TTL Output 3

    # Input signals to the PLogic card
    galvo_trigger_addr: int = 43  # Input from galvo (slice start)
    clock_source_addr: int = 192  # Internal 4kHz clock

    # Internal PLogic Cell Assignments for state machine
    acquisition_flag_cell: int = 1
    laser_clock_source_cell: int = 2
    laser_counter_cell_1: int = 3
    laser_counter_cell_2: int = 4
    laser_on_cell: int = 10
    camera_delay_cell: int = 12

    # Calibration & Timing
    slice_calibration_slope_um_per_deg: float = 100.0
    slice_calibration_offset_um: float = 0.0
    pulses_per_ms: float = 4.0
    delay_before_scan_ms: float = 0.0
    line_scans_per_slice: int = 1
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
