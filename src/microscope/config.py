# microscope/config.py
import os
from dataclasses import dataclass

# --- Demo Mode Check ---
USE_DEMO_CONFIG = os.environ.get("MICROSCOPE_DEMO") in ("1", "true", "True")


# --- Acquisition Settings ---
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
        """Derived camera exposure time from the laser duration."""
        return self.laser_trig_duration_ms + 1.95

    @property
    def delay_before_laser_ms(self) -> float:
        """Derived laser delay time from the camera delay."""
        return self.delay_before_camera_ms + 1.25


# --- Hardware Constants ---
@dataclass
class HardwareConstants:
    """Stores fixed hardware configuration and device labels."""

    cfg_path: str = "" if USE_DEMO_CONFIG else "hardware_profiles/20250523-OPM.cfg"

    # --- Device Labels ---
    galvo_a_label: str = "Scanner:AB:33"
    piezo_a_label: str = "PiezoStage:P:34"
    camera_a_label: str = "Camera-1"
    plogic_label: str = "PLogic:E:36"
    tiger_comm_hub_label: str = "TigerCommHub"

    # --- PLogic Address Definitions ---
    # These map the physical TTL lines on the Tiger backplane.
    # Outputs from PLogic card:
    PLOGIC_OUTPUT_CAMERA: int = 41  # Backplane TTL 0 -> Camera Trigger
    PLOGIC_OUTPUT_LASER: int = 42  # Backplane TTL 1 -> Laser Trigger

    # Inputs to PLogic card:
    PLOGIC_INPUT_GALVO: int = 43  # Backplane TTL 2 <- Galvo "slice start" signal
    PLOGIC_INPUT_CLOCK: int = 192  # Internal 4kHz clock signal

    # --- PLogic Cell Assignments ---
    # These are arbitrary assignments for the internal logic cells.
    PLOGIC_CELL_CAMERA_DELAY: int = 12
    PLOGIC_CELL_LASER_DELAY: int = 11
    PLOGIC_CELL_LASER_PULSE: int = 10

    # --- Hardware Timing & Calibration ---
    pulses_per_ms: float = 4.0  # From the PLogic card's 4kHz clock
    slice_calibration_slope_um_per_deg: float = 100.0
    slice_calibration_offset_um: float = 0.0

    # --- SPIM Scan Parameters ---
    delay_before_scan_ms: float = 0.0
    line_scans_per_slice: int = 1
    num_sides: int = 1
    first_side_is_a: bool = True
    scan_opposite_directions: bool = False
    sheet_width_deg: float = 0.5
    sheet_offset_deg: float = 0.0
    delay_before_side_ms: float = 0.0
    camera_mode_is_overlap: bool = False


# Instantiate the constants for global use
HW = HardwareConstants()
if USE_DEMO_CONFIG:
    print("...RUNNING IN DEMO MODE...")
