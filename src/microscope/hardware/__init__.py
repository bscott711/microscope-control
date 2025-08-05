# src/microscope/hardware/__init__.py
"""
microscope.hardware
Public API for hardware control functions.
This module exposes a simplified interface to the underlying hardware modules.
"""

# Import Camera functions
from .camera import (
    check_and_reset_camera_trigger_modes,
    reset_cameras_to_internal,
    set_camera_for_hardware_trigger,
)

# Import core utilities
from .core import get_property, send_tiger_command, set_property

# Import Galvo functions
from .galvo import (
    configure_galvo_for_spim_scan,
    trigger_spim_scan_acquisition,
)

# Import Initializer function
from .initializer import initialize_system_hardware

# Import PLogic functions
from .plogic import (
    close_global_shutter,
    configure_plogic_for_dual_nrt_pulses,
    disable_live_laser,
    enable_live_laser,
    open_global_shutter,
)

# Define the public API
__all__ = [
    # Core
    "get_property",
    "set_property",
    "send_tiger_command",
    # PLogic
    "open_global_shutter",
    "close_global_shutter",
    "configure_plogic_for_dual_nrt_pulses",
    "enable_live_laser",
    "disable_live_laser",
    # Galvo
    "configure_galvo_for_spim_scan",
    "trigger_spim_scan_acquisition",
    # Camera
    "check_and_reset_camera_trigger_modes",
    "set_camera_for_hardware_trigger",
    "reset_cameras_to_internal",
    # Initializer
    "initialize_system_hardware",
]
