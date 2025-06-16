from __future__ import annotations

from typing import TYPE_CHECKING

from .asi_commands import ASIGalvoCommands
from .models import GalvoLaserMode, GalvoScanMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class GalvoController:
    """High-level controller for ASI galvo mirrors and scanning."""

    def __init__(
        self, galvo_x_label: str, galvo_y_label: str, tiger_hub_label: str = "ASITiger", mmc: CMMCorePlus | None = None
    ) -> None:
        self._mmc = mmc or CMMCorePlus.instance()
        self.x_axis = galvo_x_label
        self.y_axis = galvo_y_label
        self.asi = ASIGalvoCommands(tiger_hub_label, self._mmc)

    def setup_raster_scan(
        self,
        x_amplitude_mv: float,
        y_amplitude_mv: float,
        scan_rate_hz: float,
        num_lines: int,
        offset_mv: tuple[float, float] = (0, 0),
    ):
        period_ms = int(1000 / scan_rate_hz)
        self.asi.set_single_axis_offset(self.x_axis, offset_mv[0])
        self.asi.set_single_axis_amplitude(self.x_axis, x_amplitude_mv / 2)
        self.asi.set_single_axis_period(self.x_axis, period_ms)
        self.asi.set_single_axis_mode(self.x_axis, GalvoScanMode.TRIANGLE, enabled=True)
        slow_start = offset_mv[1] - (y_amplitude_mv / 2)
        slow_end = offset_mv[1] + (y_amplitude_mv / 2)
        self.asi.setup_raster_scan(self.x_axis, self.y_axis, slow_start, slow_end, num_lines)

    def setup_circular_scan(self, radius_mv: float, rate_hz: float, pattern_id: int = 1):
        """Defines and prepares a circular scan."""
        self.asi.define_circle_pattern(pattern_id, radius_mv)
        self.asi.execute_pattern(pattern_id, rate_hz)

    def start(self):
        self.asi.arm_scan(armed=True)

    def stop(self):
        self.asi.stop_scan()
        self.asi.set_single_axis_mode(self.x_axis, GalvoScanMode.SAWTOOTH, enabled=False)
        self.asi.set_laser_mode(GalvoLaserMode.OFF)

    def set_position_mv(self, x_mv: float, y_mv: float):
        self.stop()
        self._mmc.setXYPosition(self.x_axis, self.y_axis, x_mv, y_mv)
