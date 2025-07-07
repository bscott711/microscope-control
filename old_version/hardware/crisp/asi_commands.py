# hardware/crisp/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from ..common import ASIException, BaseASICommands
from .models import CrispState

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASICrispCommands(BaseASICommands):
    """
    LOW-LEVEL: Provides a complete, Pythonic interface for all custom
    ASI CRISP autofocus serial commands.
    """

    def __init__(
        self,
        mmc: CMMCorePlus,
        command_device_label: str = "CRISP",
    ) -> None:
        # Note: CRISP commands are sent directly to the CRISP device, not the hub
        super().__init__(mmc, command_device_label)
        self._port = self._mmc.getProperty(self._command_device, "Port")

    def _send(self, command: str) -> str:
        """Send a command to the CRISP device and get the response."""
        full_command = f"{self._command_device} {command}"
        self._mmc.setSerialPortCommand(self._port, full_command, "\r")
        response = self._mmc.getSerialPortAnswer(self._port, "\r")

        # Check if the response indicates an error
        if response.startswith(":N"):
            # Extract the specific error code (e.g., ":N-1") from the response
            error_code = response.split(" ")[0]
            # Now, raise the exception with the correct arguments
            raise ASIException(code=error_code, command=command)
        return response

    def _query_param(self, param: str) -> str:
        """Helper to query a parameter using 'LK [param]?' syntax."""
        response = self._send(f"LK {param}?")
        try:
            return response.split("=")[1].strip()
        except IndexError:
            raise ValueError(f"Unexpected response from CRISP query '{param}': {response}")

    def _query_value(self, command: str) -> str:
        """Helper to query a value from commands like 'GAIN?'."""
        response = self._send(command)
        return response.split(" ")[-1].strip()

    # --- State and Query Methods ---
    def get_state(self) -> CrispState:
        return CrispState(int(self._query_param("X")))

    def get_snr(self) -> float:
        return float(self._query_param("Y"))

    # --- Actions and Calibrations ---
    def lock(self):
        self._send("LK")

    def unlock(self):
        self._send("UL")

    def reset_offset(self):
        self._send("LK X=10")

    def calibrate_log_amp(self):
        self._send("LK X=2")

    def calibrate_gain(self):
        self._send("LK X=4")

    def dither(self):
        self._send("LK X=3")

    # --- Configuration Getters and Setters ---

    def set_gain(self, gain: int):
        self._send(f"G K={gain}")

    def get_gain(self) -> int:
        return int(self._query_value("G K?"))

    def set_led_intensity(self, intensity: int):
        self._send(f"L I={intensity}")

    def get_led_intensity(self) -> int:
        return int(self._query_value("L I?"))

    def set_averaging(self, num_samples: int):
        self._send(f"NA F={num_samples}")

    def get_averaging(self) -> int:
        return int(self._query_value("NA F?"))

    def set_lock_range(self, range_um: float):
        self._send(f"LR F={range_um}")

    def get_lock_range(self) -> float:
        return float(self._query_value("LR F?"))

    def set_autofocus_limit(self, limit_steps: int):
        """Sets the max motor steps CRISP will move to find focus (AFLIM)."""
        self._send(f"AL N={limit_steps}")

    def get_autofocus_limit(self) -> int:
        """Gets the max motor steps CRISP will move to find focus (AFLIM)."""
        return int(self._query_value("AL N?"))
