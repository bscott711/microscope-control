# hardware/galvo/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..common import BaseASICommands
from .models import GalvoLaserMode, GalvoScanMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIGalvoCommands(BaseASICommands):
    """
    LOW-LEVEL: Provides a complete interface for all ASI Galvo and
    laser scanning serial commands.
    """

    def __init__(
        self,
        mmc: CMMCorePlus,
        command_device_label: str = "ASITiger",
    ) -> None:
        super().__init__(mmc, command_device_label)

    def _get_axis_param(self, axis: str, param_char: str) -> str:
        """Helper to query a single-axis scan parameter."""
        response = self._send(f"{axis}SA{param_char}?")
        return response.split("=")[-1].strip()

    # --- Single-Axis Scan Getters and Setters ---
    def set_single_axis_mode(self, axis: str, mode: GalvoScanMode, enabled: bool):
        self._send(f"{axis}SAM M={mode.value} Z={int(enabled)}")

    def get_single_axis_mode(self, axis: str) -> dict:
        response = self._send(f"{axis}SAM?")
        parts = response.split(" ")
        return {"mode": int(parts[1]), "enabled": bool(int(parts[2]))}

    def set_single_axis_amplitude(self, axis: str, amplitude_mv: float):
        self._send(f"{axis}SAA F={amplitude_mv}")

    def get_single_axis_amplitude(self, axis: str) -> float:
        return float(self._get_axis_param(axis, "A"))

    def set_single_axis_offset(self, axis: str, offset_mv: float):
        self._send(f"{axis}SAO F={offset_mv}")

    def get_single_axis_offset(self, axis: str) -> float:
        return float(self._get_axis_param(axis, "O"))

    def set_single_axis_period(self, axis: str, period_ms: int):
        self._send(f"{axis}SAP F={period_ms}")

    def get_single_axis_period(self, axis: str) -> int:
        return int(self._get_axis_param(axis, "P"))

    # --- Raster and Vertical Scanning ---
    def setup_raster_scan(
        self,
        fast_axis: str,
        slow_axis: str,
        slow_start_mv: float,
        slow_end_mv: float,
        num_lines: int,
    ):
        self._send(f"SCANR {fast_axis} {slow_axis} S={slow_start_mv} E={slow_end_mv} N={num_lines}")

    def setup_vertical_scan(self, axis: str, start_mv: float, end_mv: float, lines_per_scan: int):
        """Configure a vertical sawtooth scan (SCANV)."""
        self._send(f"SCANV {axis} S={start_mv} E={end_mv} N={lines_per_scan}")

    def arm_scan(self, armed: bool = True):
        self._send(f"SCAN A={int(armed)}")

    def stop_scan(self):
        self._send(r"\ ")  # HALT command

    # --- Laser Control ---
    def set_laser_mode(self, mode: GalvoLaserMode):
        """Sets the laser output mode during scanning (LASER command)."""
        self._send(f"LASER X={mode.value}")

    def set_laser_ttl_modulation(self, bnc_input: Literal[1, 2, 3, 4]):
        """Modulate the laser with a TTL signal from a BNC input."""
        self._send(f"LASER Y={bnc_input}")
