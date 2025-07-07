# hardware/hal.py
from __future__ import annotations

from typing import TYPE_CHECKING, Callable, TypeVar, Union

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core import DeviceType

# Import all our finalized high-level controllers
from .camera import CameraHardwareController
from .crisp import CrispController
from .galvo import GalvoController
from .piezo import PiezoController
from .plogic import PLogicController
from .stage import StageHardwareController, XYStageHardwareController

# This type alias is for static analysis and helps catch errors.
if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus  # Redundant import, can be removed

    HardwareController = Union[
        CameraHardwareController,
        CrispController,
        GalvoController,
        PiezoController,
        PLogicController,
        StageHardwareController,
        XYStageHardwareController,
    ]

# A TypeVar allows the return type of a function to be inferred from its inputs.
T = TypeVar("T")


class HardwareAbstractionLayer:
    """
    Final, robust HAL that discovers all devices, stores them in a central
    registry, and provides direct-access attributes for primary components.
    """

    def __init__(self, mmc: CMMCorePlus | None = None) -> None:
        self.mmc = mmc
        self.devices: dict[str, HardwareController] = {}
        self.scanner: GalvoController | None = None
        self.plogic: PLogicController | None = None
        # FIX: Do not run discovery on initialization.
        # This will now be called explicitly from __main__ after the
        # hardware config is loaded.
        # self._discover_devices()

    # --- Convenience properties with Type-Safe Lookups ---

    def _get_device_by_role(
        self,
        role_getter: Callable[[], str],
        expected_type: type[T] | tuple[type[T], ...],
    ) -> T | None:
        """
        A type-safe helper to get a device from the registry.

        It checks if the device exists and is of the expected type, inferring
        the return type.
        """
        if not self.mmc:
            return None
        label = role_getter()
        if not label:
            return None

        device = self.devices.get(label)
        if isinstance(device, expected_type):
            return device
        return None

    @property
    def camera(self) -> CameraHardwareController | None:
        """The default camera device currently assigned in the core."""
        if not self.mmc:
            return None
        return self._get_device_by_role(self.mmc.getCameraDevice, CameraHardwareController)

    @property
    def z_stage(self) -> StageHardwareController | PiezoController | None:
        """The default focus device currently assigned in the core."""
        if not self.mmc:
            return None
        return self._get_device_by_role(
            self.mmc.getFocusDevice,
            (StageHardwareController, PiezoController),
        )

    @property
    def xy_stage(self) -> XYStageHardwareController | None:
        """The default XY stage device currently assigned in the core."""
        if not self.mmc:
            return None
        return self._get_device_by_role(self.mmc.getXYStageDevice, XYStageHardwareController)

    @property
    def autofocus(self) -> CrispController | None:
        """The default autofocus device currently assigned in the core."""
        if not self.mmc:
            return None
        return self._get_device_by_role(self.mmc.getAutoFocusDevice, CrispController)

    def _discover_devices(self) -> None:
        """
        Discovers and initializes hardware controllers for all available devices.
        """
        if not self.mmc:
            return

        print("INFO: Hardware discovery started...")
        discovered: dict[str, HardwareController] = {}

        tiger_hub_label = next(
            (dev for dev in self.mmc.getLoadedDevices() if "ASITiger" in dev),
            None,
        )

        for label in self.mmc.getLoadedDevices():
            dev_type = self.mmc.getDeviceType(label)

            if dev_type == DeviceType.CameraDevice:
                discovered[label] = CameraHardwareController(label, self.mmc)
            elif dev_type == DeviceType.XYStageDevice and tiger_hub_label:
                discovered[label] = XYStageHardwareController(label, tiger_hub_label, self.mmc)
            elif dev_type == DeviceType.StageDevice:
                if "piezo" in label.lower():
                    if tiger_hub_label:
                        discovered[label] = PiezoController(label, tiger_hub_label, self.mmc)
                elif tiger_hub_label:
                    discovered[label] = StageHardwareController(label, tiger_hub_label, self.mmc)
            elif dev_type == DeviceType.AutoFocusDevice:
                if self.mmc.hasProperty(label, "Port"):
                    discovered[label] = CrispController(label, self.mmc)
            elif "PLogic" in self.mmc.getDeviceLibrary(label):
                self.plogic = PLogicController(label, self.mmc)
                discovered[label] = self.plogic

        galvo_labels = [
            dev for dev in self.mmc.getLoadedDevices() if self.mmc.getDeviceType(dev) == DeviceType.GalvoDevice
        ]
        if len(galvo_labels) >= 2 and tiger_hub_label:
            x_galvo = next(
                (g for g in galvo_labels if "x" in g.lower()),
                galvo_labels[0],
            )
            y_galvo = next((g for g in galvo_labels if g != x_galvo), galvo_labels[1])
            self.scanner = GalvoController(x_galvo, y_galvo, tiger_hub_label, self.mmc)
            discovered["Scanner"] = self.scanner

        self.devices = discovered
        print("=" * 20)
        print("Hardware Discovery Complete. Initialized controllers for:")
        for name in self.devices:
            print(f"  - {name}")
        print("=" * 20)
