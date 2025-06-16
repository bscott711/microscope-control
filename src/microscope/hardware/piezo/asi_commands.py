from __future__ import annotations

from typing import TYPE_CHECKING

from .models import PiezoMaintainMode, PiezoMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPiezoCommands:
    """LOW-LEVEL: Provides a complete interface for all custom ASI Piezo commands."""

    def __init__(self, piezo_device_label: str, mmc: CMMCorePlus) -> None:
        self._mmc = mmc
        self._label = piezo_device_label
        # Piezo commands are sent directly to the Piezo device axis
        self._send_target = self._label

    def _send(self, command: str) -> str:
        """Sends a command to the Piezo device."""
        full_command = f"{self._send_target} {command}"
        port = self._mmc.getSerialPortName(self._label)
        self._mmc.setSerialPortCommand(port, full_command, "\r")
        response = self._mmc.getSerialPortAnswer(port, "\r")
        if ":N" in response:
            raise RuntimeError(f"ASI Piezo command failed: '{command}' -> {response}")
        return response

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
