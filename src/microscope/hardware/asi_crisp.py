from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus, main_core_singleton

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class CrispState(IntEnum):
    """An enumeration of the possible states of the CRISP system."""

    Idle = 3
    Log_Amp_Cal = 4
    Dithering = 5
    Gain_Cal = 6
    Ready = 7
    In_Focus = 8
    Focal_Plane_Found = 9
    Monitoring = 10
    Focusing = 11
    In_Lock = 12
    Focus_Lost_Recently = 13
    Out_Of_Focus = 14
    Focus_Lost = 15


class ASICrispCommands:
    """
    LOW-LEVEL: Provides a complete, Pythonic interface for all custom
    ASI CRISP autofocus serial commands.
    """

    def __init__(
        self,
        crisp_device_label: str,
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or main_core_singleton()
        self._label = crisp_device_label

    def _send(self, command: str, with_dev_label: bool = True) -> str:
        """Send a command to the CRISP device and get the response."""
        full_command = f"{self._label} {command}" if with_dev_label else command
        port = self._mmc.getSerialPortName(self._label)
        self._mmc.setSerialPortCommand(port, full_command, "\r")
        return self._mmc.getSerialPortAnswer(port, "\r")

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
