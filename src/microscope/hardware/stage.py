from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus import Device, DeviceProperty, main_core_singleton

from .asi_tiger_stage import ASITigerStageCommands

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class StageHardwareController(Device):
    """
    A final, comprehensive, event-driven stage controller.

    This class handles standard stage properties (position) and actions
    (home, stop, relative moves) by subclassing `pymmcore_plus.Device`.

    All advanced, ASI-specific functionality (tuning, limits, Z-stacks, etc.)
    is delegated to the `ASITigerStageCommands` class, available via the `.asi`
    attribute, providing a complete and well-structured API.
    """

    position: DeviceProperty[float] = DeviceProperty()
    step_size: DeviceProperty[float] = DeviceProperty(is_optional=True)

    def __init__(
        self,
        device_label: str,
        tiger_hub_label: str = "ASITiger",
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or main_core_singleton()
        super().__init__(device_label)
        self.asi = ASITigerStageCommands(tiger_hub_label, self._mmc)
        self._mmc.events.stagePositionChanged.connect(self._on_stage_pos_changed)

    def _on_stage_pos_changed(self, device: str, new_pos: float) -> None:
        if device == self.label:
            print(f"INFO: Position for '{self.label}' changed to: {new_pos} µm")

    # --- Standard Actions ---

    def stop(self) -> None:
        """Immediately stops stage movement."""
        self._mmc.stop(self.label)

    def home(self) -> None:
        """Send the stage to its home position."""
        self._mmc.home(self.label)

    def wait_for_device(self) -> None:
        """Wait for the device to finish any current movement."""
        self._mmc.waitForDevice(self.label)

    def move_relative(self, distance_um: float):
        """Moves the stage by a relative amount in microns."""
        self._mmc.setRelativePosition(self.label, distance_um)

    # --- High-level wrappers for ASI commands ---

    def set_travel_limits(self, low_um: float, high_um: float):
        """Sets the software travel limits for this stage axis."""
        self.asi.set_travel_limits(self.label, low_um / 1000, high_um / 1000)
        print(f"INFO: Travel limits for '{self.label}' set to ({low_um}, {high_um}) µm.")

    def set_current_position_as_zero(self):
        """Define the current position as the new zero origin."""
        self.asi.set_current_position_as_zero(self.label)
        print(f"INFO: New zero position for '{self.label}' set.")


class XYStageHardwareController:
    """A high-level controller for a 2-axis XY stage."""

    def __init__(
        self,
        device_label: str,
        tiger_hub_label: str = "ASITiger",
        mmc: CMMCorePlus | None = None,
    ):
        self._mmc = mmc or main_core_singleton()
        self._label = device_label
        self.asi = ASITigerStageCommands(tiger_hub_label, self._mmc)
        self._mmc.events.xyStagePositionChanged.connect(self._on_xy_pos_changed)

    def _on_xy_pos_changed(self, device: str, x: float, y: float):
        if device == self._label:
            print(f"INFO: Position for '{self.label}' changed to: ({x}, {y}) µm")

    def get_position(self) -> tuple[float, float]:
        """Returns the current (X, Y) position in microns."""
        return self._mmc.getXYPosition(self._label)

    def set_position(self, x_um: float, y_um: float):
        """Moves the stage to an absolute position in microns."""
        self._mmc.setXYPosition(self._label, x_um, y_um)

    def move_relative(self, dx_um: float, dy_um: float):
        """Moves the stage by a relative amount in microns."""
        self._mmc.setRelativeXYPosition(self._label, dx_um, dy_um)
