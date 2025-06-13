# src/microscope/hardware/camera.py
from typing import Callable

from pymmcore_plus import CMMCorePlus

from ..config import HW


class CameraController:
    """A controller for camera-specific hardware properties."""

    def __init__(self, mmc: CMMCorePlus, set_property: Callable[..., None]):
        self.mmc = mmc
        self._set_property = set_property

    @property
    def label(self) -> str:
        """The Micro-Manager device label for this camera."""
        return HW.camera_a_label

    def set_trigger_mode(self, mode: str):
        """Sets the camera's trigger mode (e.g., 'Internal' or 'Edge Trigger')."""
        self._set_property(self.label, "TriggerMode", mode)
