from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus, Device, DeviceProperty

from .asi_commands import ASIPiezoCommands
from .models import PiezoMode

if TYPE_CHECKING:
    from .models import PiezoMaintainMode


class PiezoController(Device):
    """
    A final, comprehensive controller for an ASI Piezo stage.

    This class provides a high-level API for all major Piezo functions,
    including standard positioning and advanced ASI-specific configurations.
    """

    position: DeviceProperty[float] = DeviceProperty()

    def __init__(self, device_label: str, mmc: CMMCorePlus | None = None) -> None:
        self._mmc = mmc or CMMCorePlus.instance()
        super().__init__(device_label)
        self.asi = ASIPiezoCommands(device_label, self._mmc)
        self._mmc.events.stagePositionChanged.connect(self._on_stage_pos_changed)

    def _on_stage_pos_changed(self, device: str, new_pos: float) -> None:
        if device == self.label:
            print(f"INFO: Position for Piezo '{self.label}' changed to: {new_pos} µm")

    @property
    def operating_mode(self) -> PiezoMode:
        """The current operating mode of the Piezo (e.g., closed loop)."""
        return self.asi.get_operating_mode()

    @operating_mode.setter
    def operating_mode(self, mode: PiezoMode):
        self.asi.set_operating_mode(mode)

    @property
    def maintain_mode(self) -> PiezoMaintainMode:
        """The maintain mode, controlling overshoot algorithms."""
        return self.asi.get_maintain_mode()

    @maintain_mode.setter
    def maintain_mode(self, mode: PiezoMaintainMode):
        self.asi.set_maintain_mode(mode)

    def run_calibration(self):
        """Runs the Piezo's auto-calibration routine."""
        print(f"INFO: Starting calibration for Piezo '{self.label}'...")
        self.asi.run_calibration()
        self._mmc.waitForDevice(self.label)
        print("INFO: Piezo calibration complete.")

    def wait_for_device(self):
        """Waits for the Piezo to finish any current movement."""
        self._mmc.waitForDevice(self.label)
