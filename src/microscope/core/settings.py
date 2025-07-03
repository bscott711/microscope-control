"""
settings.py

Data classes for acquisition settings and configuration.
"""

from dataclasses import dataclass

__all__ = ["AcquisitionSettings"]


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
