# src/microscope/hardware/piezo/controller.py
from __future__ import annotations

from typing import TYPE_CHECKING

# FIX: Use absolute imports from the public API to avoid path resolution issues.
from pymmcore_plus.core import StageDevice

from microscope.hardware.piezo.asi_commands import ASIPiezoCommands
from microscope.hardware.piezo.models import PiezoInfo

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class PiezoController:
    """
    A high-level controller for a piezo device.
    """

    device: StageDevice

    def __init__(self, device_label: str, mmc: CMMCorePlus):
        self._mmc = mmc
        device = self._mmc.getDeviceObject(device_label)

        if not isinstance(device, StageDevice):
            raise TypeError(f"Device {device_label!r} is not a StageDevice, but a {type(device).__name__}")
        self.device = device
        self.label = self.device.label
        self._asi = ASIPiezoCommands(mmc=self._mmc, command_device_label=self.label)

    def get_info(self) -> PiezoInfo:
        """
        Gets status info from the piezo, parses it, and returns a PiezoInfo object.
        """
        # This implementation assumes the _asi object has methods to get status.
        # Since ASIPiezoCommands does not have a `get_info` method,
        # we must build the PiezoInfo object from other available methods.
        current_pos = self.get_position()
        # NOTE: The following are placeholders as min/max limits are not
        # directly available via a simple command in the provided asi_commands.
        # This would need to be expanded based on other properties or commands.
        axis = "P"  # Assuming 'P' for a piezo stage
        limit_min = 0.0
        limit_max = 100.0

        return PiezoInfo(
            axis=axis,
            limit_min=limit_min,
            limit_max=limit_max,
            current_pos=current_pos,
        )

    def get_position(self) -> float:
        """Returns the current position of the piezo stage in microns."""
        return self._mmc.getPosition(self.label)

    def set_position(self, position: float):
        """Sets the position of the piezo stage in microns."""
        self._mmc.setPosition(self.label, position)
