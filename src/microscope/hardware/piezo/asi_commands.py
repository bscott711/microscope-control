# hardware/piezo/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from ..common import BaseASICommands
from .models import PiezoMaintainMode, PiezoMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPiezoCommands(BaseASICommands):
    """LOW-LEVEL: Provides a complete interface for all custom ASI Piezo commands."""

    def __init__(self, mmc: CMMCorePlus, command_device_label: str = "PIEZO") -> None:
        # Piezo commands are sent directly to the Piezo device axis
        super().__init__(mmc, command_device_label)
        self._port = self._mmc.getProperty(self._command_device, "Port")

    def _send(self, command: str) -> str:
        """Sends a command to the Piezo device."""
        full_command = f"{self._command_device} {command}"
        self._mmc.setSerialPortCommand(self._port, full_command, "\r")
        return self._mmc.getSerialPortAnswer(self._port, "\r")

    def get_operating_mode(self) -> PiezoMode:
        """Gets the current operating mode (PZ Z? command)."""
        response = self._send("PZ Z?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMode(mode_val)

    def set_operating_mode(self, mode: PiezoMode):
        """Sets the operating mode (PZ Z=... command)."""
        self._send(f"PZ Z={mode.value}")

    def get_maintain_mode(self) -> PiezoMaintainMode:
        """Gets the maintain/overshoot algorithm mode (MA? command)."""
        response = self._send("MA?")
        mode_val = int(float(response.split("=")[-1].strip()))
        return PiezoMaintainMode(mode_val)

    def set_maintain_mode(self, mode: PiezoMaintainMode):
        """Sets the maintain/overshoot algorithm mode (MA=... command)."""
        self._send(f"MA M={mode.value}")

    def run_calibration(self):
        """Runs the Piezo's auto-calibration routine (PZC command)."""
        self._send("PZC")

    def get_info(self) -> str:
        """Returns diagnostic information about the Piezo card (PZINFO)."""
        return self._send("PZINFO")
