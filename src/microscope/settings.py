# src/microscope/settings.py
"""
Configuration dataclasses for the microscope control application.

This module centralizes settings to make them easily accessible to different
parts of the application, such as the GUI and the acquisition engine.
"""

from dataclasses import dataclass


@dataclass
class AcquisitionSettings:
    """Stores all user-configurable acquisition parameters."""

    num_slices: int = 10
    step_size_um: float = 1.0
    laser_trig_duration_ms: float = 10.0
    piezo_center_um: float = -31.0
    time_points: int = 1
    time_interval_s: float = 0.0
    is_minimal_interval: bool = True
    should_save: bool = False
    save_dir: str = ""
    save_prefix: str = "acquisition"

    @property
    def camera_exposure_ms(self) -> float:
        """Derived camera exposure time."""
        return self.laser_trig_duration_ms + 1.95

    @property
    def delay_before_camera_ms(self) -> float:
        """A fixed hardware-related delay."""
        return 18.0

    @property
    def delay_before_laser_ms(self) -> float:
        """Derived laser delay time."""
        return self.delay_before_camera_ms + 1.25


@dataclass
class HardwareConstants:
    """Stores fixed hardware configuration and device labels."""

    CFG_PATH: str = "hardware_profiles/20250523-OPM.cfg"

    # Device Labels
    CAMERA_A_LABEL: str = "Camera-1"
    TIGER_COMM_HUB_LABEL: str = "TigerCommHub"
    GALVO_A_LABEL: str = "Scanner:AB:33"
    PLOGIC_LABEL: str = "PLogic:E:36"
    XY_STAGE_LABEL: str = "XYStage:XY:31"
    Z_PIEZO_LABEL: str = "PiezoStage:P:34"
    Z_STAGE_LABEL: str = "ZStage:Z:32"
    FILTER_Z_STAGE_LABEL: str = "ZStage:F:35"

    # PLogic addresses and presets
    PLOGIC_CAMERA_TRIGGER_TTL_ADDR: int = 44
    PLOGIC_LASER_TRIGGER_TTL_ADDR: int = 45
    PLOGIC_GALVO_TRIGGER_TTL_ADDR: int = 43
    PLOGIC_4KHZ_CLOCK_ADDR: int = 192
    PLOGIC_LASER_ON_CELL: int = 10
    PLOGIC_LASER_PRESET_NUM: int = 5
    PLOGIC_DELAY_BEFORE_LASER_CELL: int = 11  # ← Added
    PLOGIC_DELAY_BEFORE_CAMERA_CELL: int = 12  # ← Added

    PULSES_PER_MS: float = 4.0

    # Calibration
    SLICE_CALIBRATION_SLOPE_UM_PER_DEG: float = 100.0
    SLICE_CALIBRATION_OFFSET_UM: float = 0.0

    # SPIM Parameters
    DELAY_BEFORE_SCAN_MS: float = 0.0
    LINE_SCANS_PER_SLICE: int = 1
    LINE_SCAN_DURATION_MS: float = 1.0
    NUM_SIDES: int = 1
    FIRST_SIDE_IS_A: bool = True
    SCAN_OPPOSITE_DIRECTIONS: bool = False
    SHEET_WIDTH_DEG: float = 0.5
    SHEET_OFFSET_DEG: float = 0.0
    DELAY_BEFORE_SIDE_MS: float = 0.0
    CAMERA_MODE_IS_OVERLAP: bool = False
