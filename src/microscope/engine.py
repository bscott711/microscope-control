# src/microscope/engine.py
"""
Acquisition Engine Module

This module contains the core logic for running acquisition sequences. It is
designed to be run in a separate thread from the GUI to ensure responsiveness.
"""

import os
import time
from datetime import datetime

import numpy as np
import tifffile
from PySide6.QtCore import QObject, Signal

from .hardware import HardwareController
from .settings import AcquisitionSettings


class AcquisitionEngine(QObject):
    """
    The core engine for managing acquisition sequences.

    It runs in a separate worker thread and communicates with the GUI via signals.
    """

    # --- Signals for GUI Communication ---
    # Emitted when a new image is acquired and ready for display
    new_image_ready = Signal(np.ndarray)
    # Emitted to update the status bar in the GUI
    status_updated = Signal(str)
    # Emitted when the entire acquisition sequence (all time points) is finished
    acquisition_finished = Signal()

    def __init__(
        self,
        hw_controller: HardwareController,
        acq_settings: AcquisitionSettings,
    ):
        """
        Initializes the AcquisitionEngine.

        Args:
            hw_controller: An instance of the HardwareController.
            acq_settings: A dataclass with all the acquisition parameters.
        """
        super().__init__()
        self.hw = hw_controller
        self.settings = acq_settings

        # --- State Flags ---
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
            self.pixel_size_um = self.hw.get_pixel_size_um()

            for t in range(self.settings.time_points):
                if self._cancel_requested:
                    self.status_updated.emit("Acquisition cancelled.")
                    break

                current_time_point = t + 1
                self.status_updated.emit(f"Starting Time Point {current_time_point}/{self.settings.time_points}...")
                volume_start_time = time.monotonic()
                self.current_volume_images.clear()

                self.hw.setup_for_acquisition(self.settings)
                self._acquire_volume()

                if self._cancel_requested:
                    self.status_updated.emit("Acquisition cancelled.")
                    break

                # Save data if requested
                self._save_current_volume(current_time_point)

                # Calculate delay for the next time point
                volume_duration = time.monotonic() - volume_start_time
                if current_time_point < self.settings.time_points:
                    delay = self._calculate_inter_volume_delay(volume_duration)
                    self.status_updated.emit(f"Waiting {delay:.1f}s for next time point...")
                    time.sleep(delay)

        except Exception as e:
            self.status_updated.emit(f"Error: {e}")
            print(f"An error occurred in the acquisition engine: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("Engine finishing up...")
            self.hw.final_cleanup()
            self.acquisition_finished.emit()
            self._is_running = False

    def _acquire_volume(self):
        """Acquires a single Z-stack."""
        self.hw.mmc.startSequenceAcquisition(self.settings.num_slices, 0, True)
        self.hw.trigger_acquisition()

        images_acquired = 0
        while images_acquired < self.settings.num_slices:
            if self._cancel_requested:
                break
            if self.hw.mmc.getRemainingImageCount() > 0:
                tagged_img = self.hw.mmc.popNextTaggedImage()
                images_acquired += 1
                img = tagged_img.pix.reshape(self.hw.mmc.getImageHeight(), self.hw.mmc.getImageWidth())
                self.new_image_ready.emit(img)
                if self.settings.should_save:
                    self.current_volume_images.append(img)
            else:
                time.sleep(0.001)  # Small sleep to prevent busy-waiting

        self.hw.mmc.stopSequenceAcquisition()

    def _save_current_volume(self, time_point: int):
        """Saves the collected images for the most recent volume."""
        if not self.settings.should_save or not self.current_volume_images:
            return

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
        """Calculates the necessary pause between volumes."""
        if self.settings.is_minimal_interval:
            return 0.0
        return max(0, self.settings.time_interval_s - volume_duration)

    def cancel(self):
        """Flags the acquisition to be cancelled safely."""
        if self._is_running:
            self._cancel_requested = True
