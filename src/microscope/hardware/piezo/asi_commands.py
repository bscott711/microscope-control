# src/microscope/hardware/piezo/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from microscope.hardware.common import BaseASICommands
from microscope.hardware.piezo.models import PiezoMaintainMode, PiezoMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPiezoCommands(BaseASICommands):
    """LOW-LEVEL: Provides a complete interface for all custom ASI Piezo commands."""

    def __init__(
        self,
        mmc: CMMCorePlus,
        command_device_label: str,
        piezo_device_label: str,
    ) -> None:
        super().__init__(mmc, command_device_label)
        self._piezo_label = piezo_device_label

        try:
            self._axis = self._piezo_label.split(":")[1]
        except IndexError as e:
            raise ValueError(f"Could not parse axis from Piezo label: {self._piezo_label}") from e

        device_library = self._mmc.getDeviceLibrary(self._piezo_label)
        self._is_demo = "DemoCamera" in device_library

    def get_operating_mode(self) -> PiezoMode:
        """Gets the current operating mode (PZ command)."""
        if self._is_demo:
            return PiezoMode.CLOSED_LOOP_INTERNAL
        response = self._send(f"PZ {self._axis}?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMode(mode_val)

    def set_operating_mode(self, mode: PiezoMode):
        """Sets the operating mode (PZ command)."""
        self._send(f"PZ {self._axis}={mode.value}")

    def get_maintain_mode(self) -> PiezoMaintainMode:
        """Gets the maintain/overshoot algorithm mode (MA? command)."""
        if self._is_demo:
            return PiezoMaintainMode.DEFAULT
        response = self._send(f"MA {self._axis}?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMaintainMode(mode_val)

    def set_maintain_mode(self, mode: PiezoMaintainMode):
        """Sets the maintain/overshoot algorithm mode (MA=... command)."""
        self._send(f"MA {self._axis}={mode.value}")
