# src/microscope/core/hardware/__init__.py

"""
Initializes the hardware package.

This file makes the 'hardware' directory a Python package and exposes all public
hardware control functions from their respective modules. This allows other parts
of the application to import them from a single, consistent namespace.
"""

from .camera import set_camera_for_hardware_trigger, set_camera_trigger_mode_level_high
from .galvo import configure_galvo_for_spim_scan, trigger_spim_scan_acquisition
from .plogic import (
    close_global_shutter,
    configure_plogic_for_dual_nrt_pulses,
    disable_live_laser,
    enable_live_laser,
    open_global_shutter,
)
from .utils import get_property, set_property

__all__ = [
    # camera.py
    "set_camera_for_hardware_trigger",
    "set_camera_trigger_mode_level_high",
    # galvo.py
    "configure_galvo_for_spim_scan",
    "trigger_spim_scan_acquisition",
    # plogic.py
    "close_global_shutter",
    "configure_plogic_for_dual_nrt_pulses",
    "disable_live_laser",
    "enable_live_laser",
    "open_global_shutter",
    # utils.py
    "get_property",
    "set_property",
]
