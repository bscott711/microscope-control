from __future__ import annotations

from typing import TYPE_CHECKING

from .models import GalvoLaserMode, GalvoScanMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIGalvoCommands:
    """LOW-LEVEL: Complete interface for ASI Galvo and laser scanning commands."""

    def __init__(self, tiger_hub_label: str, mmc: CMMCorePlus) -> None:
        self._mmc = mmc
        self._hub = tiger_hub_label

    def _send(self, command: str) -> str:
        self._mmc.setProperty(self._hub, "SerialCommand", command)
        response = self._mmc.getProperty(self._hub, "SerialResponse")
        if ":N" in response:
            raise RuntimeError(f"ASI command failed: '{command}' -> {response}")
        return response

    def set_single_axis_mode(self, axis: str, mode: GalvoScanMode, enabled: bool):
        self._send(f"{axis}SAM M={mode.value} Z={int(enabled)}")

    def set_single_axis_amplitude(self, axis: str, amplitude_mv: float):
        self._send(f"{axis}SAA F={amplitude_mv}")

    def set_single_axis_offset(self, axis: str, offset_mv: float):
        self._send(f"{axis}SAO F={offset_mv}")

    def set_single_axis_period(self, axis: str, period_ms: int):
        self._send(f"{axis}SAP F={period_ms}")

    def setup_raster_scan(
        self, fast_axis: str, slow_axis: str, slow_start_mv: float, slow_end_mv: float, num_lines: int
    ):
        self._send(f"SCANR {fast_axis} {slow_axis} S={slow_start_mv} E={slow_end_mv} N={num_lines}")

    def arm_scan(self, armed: bool = True):
        self._send(f"SCAN A={int(armed)}")

    def stop_scan(self):
        self._send(r"\ ")

    def set_laser_mode(self, mode: GalvoLaserMode):
        self._send(f"LASER X={mode.value}")

    def set_ttl_output_mode(self, axis: str, mode: int):
        self._send(f"TTL Y={mode}")

    def define_circle_pattern(self, pattern_id: int, radius_mv: float, points: int = 100):
        """Defines a circular pattern in the controller's memory."""
        self._send(f"MM Y={pattern_id} X=C R={radius_mv} N={points}")

    def execute_pattern(self, pattern_id: int, rate_hz: float):
        """Executes a pre-defined pattern (MULTIMV command)."""
        self._send(f"MM Y={pattern_id} F={rate_hz}")
