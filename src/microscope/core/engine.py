# src/microscope/core/engine.py
import os
import time
import traceback
from datetime import datetime

import numpy as np
import tifffile
from PySide6.QtCore import QObject, Signal

from ..config import AcquisitionSettings

# Updated import for the new HAL
from ..hardware.hal import HardwareAbstractionLayer, mmc


class AcquisitionEngine(QObject):
    """
    The core engine for managing acquisition sequences.
    """

    new_image_ready = Signal(np.ndarray)
    status_updated = Signal(str)
    acquisition_finished = Signal()

    def __init__(self, hal: HardwareAbstractionLayer, settings: AcquisitionSettings):
        super().__init__()
        self.hal = hal
        self.settings = settings
        self._is_running = False
        self._cancel_requested = False
        self.pixel_size_um = 1.0
        self.current_volume_images = []

    def run_acquisition(self):
        """The main worker method that executes the entire acquisition sequence."""
        self._is_running = True
        self._cancel_requested = False
        print("Acquisition engine started.")

        try:
            self.pixel_size_um = mmc.getPixelSizeUm() or 1.0

            for t in range(self.settings.time_points):
                if self._cancel_requested:
                    self.status_updated.emit("Acquisition cancelled.")
                    break

                self.status_updated.emit(f"Starting Time Point {t + 1}/{self.settings.time_points}...")
                volume_start_time = time.monotonic()
                self.current_volume_images.clear()

                # Simplified calls to the HAL
                self.hal.setup_for_acquisition(self.settings)
                self._acquire_volume()

                if self._cancel_requested:
                    self.status_updated.emit("Acquisition cancelled.")
                    break

                self._save_current_volume(t + 1)

                if t < self.settings.time_points - 1:
                    duration = time.monotonic() - volume_start_time
                    delay = self._calculate_inter_volume_delay(duration)
                    self.status_updated.emit(f"Waiting {delay:.1f}s for next time point...")
                    time.sleep(delay)

        except Exception as e:
            self.status_updated.emit(f"Error: {e}")
            traceback.print_exc()
        finally:
            print("Engine finishing up...")
            self.hal.final_cleanup(self.settings)
            self.acquisition_finished.emit()
            self._is_running = False

    def _acquire_volume(self):
        """Acquires a single Z-stack."""
        num_slices = self.settings.num_slices  # Use settings directly
        mmc.startSequenceAcquisition(num_slices, 0, True)
        self.hal.start_acquisition()

        images_acquired = 0
        while images_acquired < num_slices:
            if self._cancel_requested:
                break
            if mmc.getRemainingImageCount() > 0:
                tagged_img = mmc.popNextTaggedImage()
                images_acquired += 1
                img = tagged_img.pix.reshape(mmc.getImageHeight(), mmc.getImageWidth())
                self.new_image_ready.emit(img)
                if self.settings.should_save:
                    self.current_volume_images.append(img)
            else:
                time.sleep(0.001)

        mmc.stopSequenceAcquisition()

    def _save_current_volume(self, time_point: int):
        if not self.settings.should_save or not self.current_volume_images:
            return
        # ... (rest of the save logic is unchanged)
        save_dir = self.settings.save_dir
        prefix = self.settings.save_prefix
        if not save_dir or not prefix:
            self.status_updated.emit("Error: Save directory or prefix missing.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_T{time_point:04d}_{timestamp}.tif"
        full_path = os.path.join(save_dir, filename)

        self.status_updated.emit(f"Saving to {filename}...")
        try:
            image_stack = np.stack(self.current_volume_images, axis=0)
            metadata = {
                "axes": "ZYX",
                "PhysicalSizeZ": self.settings.step_size_um,
                "PhysicalSizeY": self.pixel_size_um,
                "PhysicalSizeX": self.pixel_size_um,
                "PhysicalSizeZUnit": "micron",
                "PhysicalSizeYUnit": "micron",
                "PhysicalSizeXUnit": "micron",
            }
            tifffile.imwrite(full_path, image_stack, imagej=True, metadata=metadata)
            print(f"Save complete: {filename}")
        except Exception as e:
            self.status_updated.emit("Error: File save failed.")
            print(f"Error saving file: {e}")

    def _calculate_inter_volume_delay(self, volume_duration: float) -> float:
        if self.settings.is_minimal_interval:
            return 0.0
        return max(0, self.settings.time_interval_s - volume_duration)

    def cancel(self):
        if self._is_running:
            self._cancel_requested = True
