# hardware/piezo/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from microscope.hardware.common import BaseASICommands
from microscope.hardware.piezo.models import PiezoMaintainMode, PiezoMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPiezoCommands(BaseASICommands):
    """LOW-LEVEL: Provides a complete interface for all custom ASI Piezo commands."""

    def __init__(self, mmc: CMMCorePlus, command_device_label: str = "PIEZO") -> None:
        super().__init__(mmc, command_device_label)

        # This logic correctly handles both demo and real hardware
        device_library = self._mmc.getDeviceLibrary(self._command_device)
        self._is_demo = "DemoCamera" in device_library

        if self._is_demo:
            self._port = None
        else:
            if not self._mmc.hasProperty(self._command_device, "Port"):
                raise RuntimeError(
                    f"Device {self._command_device} has no 'Port' property. Cannot initialize ASI commands."
                )
            self._port = self._mmc.getProperty(self._command_device, "Port")

    def _send(self, command: str) -> str:
        """Sends a command to the Piezo device."""
        # FIX: Use an if/else block to satisfy static analysis.
        # This makes it explicit that the serial commands are only ever
        # called when self._port is a string.
        if self._is_demo:
            return ""
        else:
            full_command = f"{self._command_device} {command}"
            # Pylance is now happy because self._port can only be a string here
            self._mmc.setSerialPortCommand(self._port, full_command, "\r")  # type: ignore
            return self._mmc.getSerialPortAnswer(self._port, "\r")  # type: ignore

    def get_operating_mode(self) -> PiezoMode:
        """Gets the current operating mode (PZ Z? command)."""
        if self._is_demo:
            return PiezoMode.CLOSED_LOOP_INTERNAL
        response = self._send("PZ Z?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMode(mode_val)

    def set_operating_mode(self, mode: PiezoMode):
        """Sets the operating mode (PZ Z=... command)."""
        self._send(f"PZ Z={mode.value}")

    def get_maintain_mode(self) -> PiezoMaintainMode:
        """Gets the maintain/overshoot algorithm mode (MA? command)."""
        if self._is_demo:
            return PiezoMaintainMode.DEFAULT
        response = self._send("MA?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMaintainMode(mode_val)

    def set_maintain_mode(self, mode: PiezoMaintainMode):
        """Sets the maintain/overshoot algorithm mode (MA=... command)."""
        self._send(f"MA={mode.value}")
