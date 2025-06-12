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

    # These will be set by the GUI in the future
    num_slices: int = 10
    step_size_um: float = 1.0
    laser_trig_duration_ms: float = 10.0
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

    # NOTE: In a real-world scenario, you might load these from a config file
    PIEZO_CENTER_UM: float = -31.0
    CFG_PATH: str = "hardware_profiles/20250523-OPM.cfg"
    # Device labels
    GALVO_A_LABEL: str = "Scanner:AB:33"
    PIEZO_A_LABEL: str = "PiezoStage:P:34"
    CAMERA_A_LABEL: str = "Camera-1"
    PLOGIC_LABEL: str = "PLogic:E:36"
    TIGER_COMM_HUB_LABEL: str = "TigerCommHub"
    # PLogic addresses and presets
    PLOGIC_CAMERA_TRIGGER_TTL_ADDR: int = 44
    PLOGIC_LASER_TRIGGER_TTL_ADDR: int = 45
    PLOGIC_GALVO_TRIGGER_TTL_ADDR: int = 43
    PLOGIC_4KHZ_CLOCK_ADDR: int = 192
    PLOGIC_LASER_ON_CELL: int = 10
    PLOGIC_LASER_PRESET_NUM: int = 5
    PLOGIC_DELAY_BEFORE_LASER_CELL: int = 11
    PLOGIC_DELAY_BEFORE_CAMERA_CELL: int = 12
    PULSES_PER_MS: float = 4.0
    # Calibration
    SLICE_CALIBRATION_SLOPE_UM_PER_DEG: float = 100.0
    SLICE_CALIBRATION_OFFSET_UM: float = 0.0
