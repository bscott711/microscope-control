# src/microscope/hardware/camera/controller.py
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

# Import the specific CameraDevice class for type hinting and validation
from pymmcore_plus.core._device import CameraDevice

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class CameraHardwareController:
    """
    A high-level controller for a camera device.

    This class uses composition to wrap a pymmcore_plus.Device object.
    """

    device: CameraDevice

    def __init__(self, device_label: str, mmc: CMMCorePlus):
        self._mmc = mmc
        device = self._mmc.getDeviceObject(device_label)

        if not isinstance(device, CameraDevice):
            raise TypeError(
                f"Device {device_label!r} is not a CameraDevice, "
                f"but a {type(device).__name__}"
            )
        self.device = device
        self.label = self.device.label

    def pop_from_buffer(self) -> np.ndarray | None:
        """Pops and returns the next image from the circular buffer, if available."""
        # FIX: These methods must be called on the core CMMCorePlus object.
        if self._mmc.getRemainingImageCount() > 0:
            return self._mmc.popNextImage()
        return None

    def get_exposure(self) -> float:
        """Returns the current exposure time in milliseconds."""
        return self._mmc.getExposure()

    def set_exposure(self, value: float):
        """Sets the exposure time in milliseconds."""
        self._mmc.setExposure(value)

    def snap(self) -> np.ndarray:
        """Snap and return an image."""
        # FIX: snap() is a convenience method on the core CMMCorePlus object.
        return self._mmc.snap()
