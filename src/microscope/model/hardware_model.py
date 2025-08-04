# src/microscope/model/hardware_model.py
"""
hardware_model.py
Data classes for acquisition settings and configuration.
This module loads hardware constants from a YAML configuration file.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

__all__ = ["AcquisitionSettings", "HardwareConstants"]


@dataclass
class AcquisitionSettings:
    """
    Stores all user-configurable acquisition parameters used by the ASI PLogic system.

    Attributes:
        num_slices: Number of Z slices per volume
        step_size_um: Step size between slices (in microns)
        laser_trig_duration_ms: Duration of laser trigger pulse (ms)
        camera_exposure_ms: Camera exposure time (ms)
    """

    num_slices: int = 3
    step_size_um: float = 1.0
    laser_trig_duration_ms: float = 10.0
    camera_exposure_ms: float = 10.0


@dataclass
class HardwareConstants:
    """
    Stores hardware-specific labels and calibration constants.
    Loads configuration from a YAML file.
    """

    # This object will hold the acquisition settings loaded from the config
    acquisition: AcquisitionSettings = field(init=False)

    # The path to the config file can be overridden at instantiation
    config_path: Path = field(default_factory=lambda: Path("hardware_profiles/default_config.yml"))

    # --- Hardware Labels ---
    galvo_a_label: str = ""
    piezo_a_label: str = ""
    camera_a_label: str = ""
    camera_b_label: str = ""
    plogic_label: str = ""
    tiger_comm_hub_label: str = ""

    # --- PLogic Address Constants (Decimal) ---
    plogic_trigger_ttl_addr: int = 0
    plogic_4khz_clock_addr: int = 0
    plogic_laser_on_cell: int = 0
    plogic_camera_cell: int = 0
    plogic_always_on_cell: int = 0
    plogic_bnc3_addr: int = 0
    plogic_bnc1_addr: int = 0

    # --- PLogic Calibration & Timing ---
    pulses_per_ms: float = 0.0
    plogic_laser_preset_num: int = 0
    slice_calibration_slope_um_per_deg: float = 0.0

    # --- PLogic Presets for Live/Snap ---
    plogic_live_mode_preset: int = 0
    plogic_idle_mode_preset: int = 0

    # --- Galvo/SPIM Timing ---
    line_scans_per_slice: int = 0
    delay_before_scan_ms: float = 0.0
    line_scan_duration_ms: float = 0.0
    delay_before_side_ms: float = 0.0

    def __post_init__(self):
        """Load configuration from the YAML file after initialization."""
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        try:
            with self.config_path.open() as f:
                config = yaml.safe_load(f)

            hw_config = config.get("hardware", {})
            acq_config = config.get("acquisition", {})

            # Set hardware attributes
            for key, value in hw_config.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                else:
                    logger.warning(f"Unknown hardware config key: {key}")

            # Create an AcquisitionSettings instance from the config values
            self.acquisition = AcquisitionSettings(**acq_config)

            logger.info(f"Hardware configuration loaded from {self.config_path}")

        except Exception as e:
            logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise
