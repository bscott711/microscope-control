# src/microscope/core/__init__.py

"""
Initializes the core package.

This file makes the 'core' directory a Python package and exposes its
public API. This allows other parts of the application to have a single,
consistent entry point for all core functionality, abstracting away the
internal module structure.
"""

from .constants import HardwareConstants
from .datastore import OMETiffWriterWithMetadata
from .engine import CustomPLogicMDAEngine
from .hardware import (
    close_global_shutter,
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    disable_live_laser,
    enable_live_laser,
    get_property,
    open_global_shutter,
    set_camera_for_hardware_trigger,
    set_camera_trigger_mode_level_high,
    set_property,
    trigger_spim_scan_acquisition,
)
from .settings import AcquisitionSettings

__all__ = [
    # constants
    "HardwareConstants",
    # datastore
    "OMETiffWriterWithMetadata",
    # engine
    "CustomPLogicMDAEngine",
    # hardware
    "close_global_shutter",
    "configure_galvo_for_spim_scan",
    "configure_plogic_for_dual_nrt_pulses",
    "disable_live_laser",
    "enable_live_laser",
    "get_property",
    "open_global_shutter",
    "set_camera_for_hardware_trigger",
    "set_camera_trigger_mode_level_high",
    "set_property",
    "trigger_spim_scan_acquisition",
    # settings
    "AcquisitionSettings",
]
