from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus import Device, DeviceProperty, main_core_singleton

if TYPE_CHECKING:
    import numpy as np
    from pymmcore_plus import CMMCorePlus


class CameraHardwareController(Device):
    """
    A final, comprehensive, event-driven camera controller.

    This class provides a high-level API for all major camera functions,
    including ROI management, temperature control, and high-speed sequence
    acquisition. It uses `pymmcore_plus.Device` for robust, declarative
    property management.
    """

    # --- Standard Properties ---
    exposure: DeviceProperty[float] = DeviceProperty()
    binning: DeviceProperty[str] = DeviceProperty()
    bit_depth: DeviceProperty[int] = DeviceProperty(read_only=True)
    gain: DeviceProperty[int] = DeviceProperty()
    ccd_temperature: DeviceProperty[float] = DeviceProperty(read_only=True, is_optional=True)
    trigger_mode: DeviceProperty[str] = DeviceProperty(is_optional=True)
    readout_rate: DeviceProperty[str] = DeviceProperty(is_optional=True)

    def __init__(
        self,
        device_label: str,
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or main_core_singleton()
        super().__init__(device_label)
        self._mmc.setCameraDevice(self.device_label)
        self._mmc.events.propertyChanged.connect(self._on_property_changed)

    def _on_property_changed(self, device: str, prop: str, value: str) -> None:
        if device == self.label:
            print(f"INFO: Camera property '{prop}' for '{self.label}' changed to: {value}")

    # --- Region of Interest (ROI) ---

    def set_roi(self, x: int, y: int, width: int, height: int) -> None:
        """
        Sets the camera's Region of Interest (ROI).

        Parameters
        ----------
        x : int
            The x-offset of the ROI.
        y : int
            The y-offset of the ROI.
        width : int
            The width of the ROI.
        height : int
            The height of the ROI.
        """
        self._mmc.setROI(self.label, x, y, width, height)
        print(f"INFO: ROI for '{self.label}' set to (x={x}, y={y}, w={width}, h={height})")

    def get_roi(self) -> tuple[int, int, int, int]:
        """Returns the current ROI as (x, y, width, height)."""
        return self._mmc.getROI(self.label)

    def clear_roi(self) -> None:
        """Resets the camera to its full frame."""
        self._mmc.clearROI()
        print(f"INFO: ROI for '{self.label}' cleared to full frame.")

    # --- Acquisition Methods ---

    def snap(self) -> np.ndarray:
        """
        Acquires a single image from the camera.

        This is a blocking call. For high-speed acquisitions, use the
        sequence acquisition methods.
        """
        self._mmc.snap()
        return self._mmc.getImage()

    def start_sequence_acquisition(self, num_images: int = 2**31 - 1, interval_ms: float = 0):
        """
        Starts a non-blocking, buffered sequence acquisition.

        This is the preferred method for "live" mode or high-speed acquisitions,
        as images are stored in the camera/adapter's circular buffer. Images
        can be retrieved with `pop_from_buffer()`.

        Parameters
        ----------
        num_images : int
            The number of images to acquire. Defaults to a very large number
            for continuous acquisition.
        interval_ms : float
            The interval between images in milliseconds.
        """
        self._mmc.startSequenceAcquisition(self.label, num_images, interval_ms, True)
        print(f"INFO: Started sequence acquisition for '{self.label}'.")

    def stop_sequence_acquisition(self) -> None:
        """Stops the ongoing sequence acquisition."""
        self._mmc.stopSequenceAcquisition(self.label)
        print(f"INFO: Stopped sequence acquisition for '{self.label}'.")

    def pop_from_buffer(self) -> np.ndarray | None:
        """
        Pops and returns the next image from the circular buffer.

        Returns None if the buffer is empty.
        """
        if self._mmc.getRemainingImageCount() > 0:
            return self._mmc.popNextImage()
        return None
