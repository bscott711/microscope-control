# hardware/galvo/controller.py
from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus

from .asi_commands import ASIGalvoCommands
from .models import GalvoLaserMode, GalvoScanMode

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class GalvoController:
    """
    A final, comprehensive controller for ASI galvo mirrors and scanning.

    This class provides a high-level API to perform common scanning operations
    like raster and line scans, with fully integrated laser control. All
    low-level serial commands are delegated to the `ASIGalvoCommands` class,
    available via the `.asi` attribute.
    """

    def __init__(
        self,
        galvo_x_label: str,
        galvo_y_label: str,
        tiger_hub_label: str = "ASITiger",
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or CMMCorePlus.instance()
        self.x_axis = galvo_x_label
        self.y_axis = galvo_y_label
        self.asi = ASIGalvoCommands(self._mmc, tiger_hub_label)

    # --- High-Level Scan Methods ---
    def setup_raster_scan(
        self,
        x_amplitude_mv: float,
        y_amplitude_mv: float,
        scan_rate_hz: float,
        num_lines: int,
        offset_mv: tuple[float, float] = (0, 0),
        laser_mode: GalvoLaserMode = GalvoLaserMode.ON_DURING_SCAN,
    ):
        """
        Configures all parameters for a raster scan, including laser output.

        This method prepares the hardware but does not start the scan.
        Call `start()` to begin the armed pattern.
        """
        # 1. Configure laser output mode
        self.asi.set_laser_mode(laser_mode)

        # 2. Configure fast axis (X) as a triangle wave
        period_ms = int(1000 / scan_rate_hz)
        self.asi.set_single_axis_offset(self.x_axis, offset_mv[0])
        self.asi.set_single_axis_amplitude(self.x_axis, x_amplitude_mv / 2)
        self.asi.set_single_axis_period(self.x_axis, period_ms)
        self.asi.set_single_axis_mode(self.x_axis, GalvoScanMode.TRIANGLE, enabled=True)

        # 3. Configure slow axis (Y) for the raster scan
        slow_start = offset_mv[1] - (y_amplitude_mv / 2)
        slow_end = offset_mv[1] + (y_amplitude_mv / 2)
        self.asi.setup_raster_scan(
            fast_axis=self.x_axis,
            slow_axis=self.y_axis,
            slow_start_mv=slow_start,
            slow_end_mv=slow_end,
            num_lines=num_lines,
        )

    def start(self):
        """Arms and starts the configured scan pattern."""
        self.asi.arm_scan(armed=True)
        print("INFO: Galvo scan armed and started.")

    def stop(self):
        """Stops all scanning activity and disables the laser output."""
        self.asi.stop_scan()
        self.asi.set_single_axis_mode(self.x_axis, GalvoScanMode.SAWTOOTH, enabled=False)
        self.asi.set_single_axis_mode(self.y_axis, GalvoScanMode.SAWTOOTH, enabled=False)
        self.asi.set_laser_mode(GalvoLaserMode.OFF)
        print("INFO: Galvo scan stopped.")

    # --- Position and State Control ---
    @property
    def position_mv(self) -> tuple[float, float]:
        """The current (X, Y) position of the galvos in millivolts."""
        x = self._mmc.getPosition(self.x_axis)
        y = self._mmc.getPosition(self.y_axis)
        return x, y

    def set_position_mv(self, x_mv: float, y_mv: float):
        """Set the static position of the galvos in millivolts."""
        self.stop()  # Ensure scanning is off before setting static position
        # Set each axis position individually.
        self._mmc.setXYPosition(self.x_axis, x_mv, y_mv)
