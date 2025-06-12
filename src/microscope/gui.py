# gui.py
import os
import time
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import filedialog, ttk
from typing import List

import numpy as np
import tifffile
from PIL import Image, ImageTk

from .config import AcquisitionSettings
from .hardware_control import (
    HardwareInterface,
    _reset_for_next_volume,  # Correctly import the specific reset function
    calculate_galvo_parameters,
    configure_devices_for_slice_scan,
    final_cleanup,
    mmc,
    trigger_slice_scan_acquisition,
)


class AcquisitionGUI:
    def __init__(self, root: tk.Tk, hw_interface: HardwareInterface):
        self.root = root
        self.hw_interface = hw_interface
        self.settings = AcquisitionSettings()
        self.root.title("ASI OPM Acquisition Control")

        # GUI Variables
        self.num_slices_var = tk.IntVar(value=self.settings.num_slices)
        self.step_size_var = tk.DoubleVar(value=self.settings.step_size_um)
        self.laser_duration_var = tk.DoubleVar(
            value=self.settings.laser_trig_duration_ms
        )
        self.num_time_points_var = tk.IntVar(value=1)
        self.time_interval_s_var = tk.DoubleVar(value=10.0)
        self.minimal_interval_var = tk.BooleanVar(value=False)
        self.should_save_var = tk.BooleanVar(value=False)
        self.save_dir_var = tk.StringVar()
        self.save_prefix_var = tk.StringVar(value="acquisition")

        # Display Variables
        self.camera_exposure_var = tk.StringVar()
        self.min_interval_display_var = tk.StringVar()
        self.total_time_display_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self._last_img = None

        # Acquisition State
        self.acquisition_in_progress = False
        self.cancel_requested = False
        self.time_points_total = 0
        self.current_time_point = 0
        self.images_expected_per_volume = 0
        self.images_popped_this_volume = 0
        self.volume_start_time = 0.0
        self.current_volume_images: List[np.ndarray] = []
        self.pixel_size_um = 1.0  # Default, will be updated

        self.create_widgets()
        self._bind_traces()
        self._update_all_estimates()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(3, weight=1)

        top_controls = ttk.Frame(main_frame)
        top_controls.grid(row=0, column=0, sticky="ew")
        top_controls.grid_columnconfigure(0, weight=1)
        top_controls.grid_columnconfigure(1, weight=1)

        ts_frame = ttk.Labelframe(top_controls, text="Time Series")
        ts_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        ts_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(ts_frame, text="Time Points").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(ts_frame, textvariable=self.num_time_points_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Label(ts_frame, text="Interval (s)").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(ts_frame, textvariable=self.time_interval_s_var).grid(
            row=1, column=1, sticky="ew", padx=5
        )
        ttk.Checkbutton(
            ts_frame, text="Minimal Interval", variable=self.minimal_interval_var
        ).grid(row=1, column=2, sticky="w", padx=5)

        vol_frame = ttk.Labelframe(top_controls, text="Volume & Timing")
        vol_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        vol_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(vol_frame, text="Slices/Volume").grid(
            row=0, column=0, sticky="w", padx=5
        )
        ttk.Entry(vol_frame, textvariable=self.num_slices_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Label(vol_frame, text="Laser Duration (ms)").grid(
            row=1, column=0, sticky="w", padx=5
        )
        ttk.Entry(vol_frame, textvariable=self.laser_duration_var).grid(
            row=1, column=1, sticky="ew", padx=5
        )

        save_frame = ttk.Labelframe(main_frame, text="Data Saving")
        save_frame.grid(row=1, column=0, sticky="ew", pady=5)
        save_frame.grid_columnconfigure(1, weight=1)
        ttk.Checkbutton(
            save_frame, text="Save to disk", variable=self.should_save_var
        ).grid(row=0, column=0, padx=5)
        dir_entry = ttk.Entry(
            save_frame, textvariable=self.save_dir_var, state="readonly"
        )
        dir_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(
            save_frame, text="Browse...", command=self._browse_save_directory
        ).grid(row=0, column=2, padx=5)
        ttk.Label(save_frame, text="File Prefix:").grid(row=0, column=3, padx=5)
        ttk.Entry(save_frame, textvariable=self.save_prefix_var).grid(
            row=0, column=4, sticky="ew", padx=5
        )

        est_frame = ttk.Labelframe(main_frame, text="Estimates")
        est_frame.grid(row=2, column=0, sticky="ew", pady=5)
        est_frame.grid_columnconfigure(1, weight=1)
        est_frame.grid_columnconfigure(3, weight=1)
        ttk.Label(est_frame, text="Camera Exposure:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        ttk.Label(est_frame, textvariable=self.camera_exposure_var).grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(est_frame, text="Min. Interval/Volume:").grid(
            row=0, column=2, sticky="w", padx=5
        )
        ttk.Label(est_frame, textvariable=self.min_interval_display_var).grid(
            row=0, column=3, sticky="w", padx=5
        )
        ttk.Label(est_frame, text="Est. Total Time:").grid(
            row=1, column=2, sticky="w", padx=5
        )
        ttk.Label(est_frame, textvariable=self.total_time_display_var).grid(
            row=1, column=3, sticky="w", padx=5
        )

        display_frame = ttk.Frame(main_frame)
        display_frame.grid(row=3, column=0, sticky="nsew", pady=5)
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        self.image_panel = ttk.Label(
            display_frame, text="Camera Image", background="black", anchor="center"
        )
        self.image_panel.grid(row=0, column=0, sticky="nsew")

        bottom_bar = ttk.Frame(main_frame)
        bottom_bar.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        bottom_bar.grid_columnconfigure(1, weight=1)
        self.run_button = ttk.Button(
            bottom_bar, text="Run Time Series", command=self.start_time_series
        )
        self.run_button.grid(row=0, column=0, padx=5)
        self.cancel_button = ttk.Button(
            bottom_bar, text="Cancel", command=self._request_cancel
        )
        self.cancel_button.grid(row=0, column=0, padx=5)
        self.cancel_button.grid_remove()
        ttk.Label(bottom_bar, textvariable=self.status_var, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Button(bottom_bar, text="Exit", command=self.root.quit).grid(
            row=0, column=2, padx=5
        )

    def _browse_save_directory(self):
        directory = filedialog.askdirectory(
            title="Select Save Directory", initialdir=self.save_dir_var.get()
        )
        if directory:
            self.save_dir_var.set(directory)

    def _bind_traces(self):
        for var in [
            self.num_time_points_var,
            self.time_interval_s_var,
            self.num_slices_var,
            self.laser_duration_var,
        ]:
            var.trace_add("write", self._update_all_estimates)
        self.minimal_interval_var.trace_add("write", self._update_all_estimates)

    def _update_all_estimates(self, *args):
        try:
            self.settings.num_slices = self.num_slices_var.get()
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.camera_exposure_var.set(f"{self.settings.camera_exposure_ms:.2f} ms")
            min_interval_s = self._calculate_minimal_interval()
            self.min_interval_display_var.set(f"{min_interval_s:.2f} s")
            total_time_str = self._calculate_total_time(min_interval_s)
            self.total_time_display_var.set(total_time_str)
        except (tk.TclError, ValueError):
            return

    def _calculate_minimal_interval(self) -> float:
        overhead_factor = 1.10
        total_exposure_ms = self.settings.num_slices * self.settings.camera_exposure_ms
        estimated_ms = total_exposure_ms * overhead_factor
        return estimated_ms / 1000.0

    def _calculate_total_time(self, min_interval_s: float) -> str:
        num_time_points = self.num_time_points_var.get()
        if self.minimal_interval_var.get():
            time_per_volume_s = min_interval_s
        else:
            user_interval_s = self.time_interval_s_var.get()
            time_per_volume_s = max(user_interval_s, min_interval_s)
        total_seconds = time_per_volume_s * num_time_points
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = int(total_seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _request_cancel(self):
        """Flags that the user has requested to cancel the acquisition."""
        print("--- Cancel Requested by User ---")
        self.status_var.set("Cancelling...")
        self.cancel_requested = True
        self.cancel_button.configure(state="disabled")

    def start_time_series(self):
        if self.acquisition_in_progress:
            return
        self.acquisition_in_progress = True
        self.cancel_requested = False
        self.run_button.grid_remove()
        self.cancel_button.grid()
        self.cancel_button.configure(state="normal")
        self.status_var.set("Initializing...")
        try:
            self.pixel_size_um = mmc.getPixelSizeUm()
            print(f"Using pixel size for metadata: {self.pixel_size_um:.3f} µm")
        except Exception:
            self.pixel_size_um = 1.0
            print("Warning: Could not get pixel size. Defaulting to 1.0 µm.")
        self.settings.step_size_um = self.step_size_var.get()
        self.time_points_total = self.num_time_points_var.get()
        self.current_time_point = 0
        self._update_all_estimates()
        print("\n--- Starting Time Series ---")
        self._start_next_volume()

    def _start_next_volume(self):
        self.current_time_point += 1
        self.current_volume_images.clear()
        self.status_var.set(
            f"Starting Time Point {self.current_time_point}/{self.time_points_total}..."
        )
        print(f"\nStarting Volume {self.current_time_point}/{self.time_points_total}")
        try:
            (
                galvo_amp,
                galvo_center,
                self.images_expected_per_volume,
            ) = calculate_galvo_parameters(self.settings)
            mmc.setCameraDevice(self.hw_interface.camera1)
            if not self.hw_interface.find_and_set_trigger_mode(
                self.hw_interface.camera1, ["Edge Trigger", "External"]
            ):
                raise RuntimeError("Failed to set external trigger mode.")
            configure_devices_for_slice_scan(
                self.settings, galvo_amp, galvo_center, self.images_expected_per_volume
            )
            mmc.setExposure(self.hw_interface.camera1, self.settings.camera_exposure_ms)
            mmc.initializeCircularBuffer()
            mmc.startSequenceAcquisition(
                self.hw_interface.camera1, self.images_expected_per_volume, 0, True
            )
            self.volume_start_time = time.monotonic()
            trigger_slice_scan_acquisition()
            self.images_popped_this_volume = 0
            self.root.after(20, self._poll_for_images)
        except Exception as e:
            print(f"Error starting volume: {e}")
            traceback.print_exc()
            self._finish_time_series()

    def _poll_for_images(self):
        if self.cancel_requested:
            self._finish_time_series(cancelled=True)
            return
        if not self.acquisition_in_progress:
            return
        if mmc.getRemainingImageCount() > 0:
            try:
                tagged_img = mmc.popNextTaggedImage()
                self.images_popped_this_volume += 1
                self.status_var.set(
                    f"Time Point {self.current_time_point}/{self.time_points_total} | "
                    f"Slice {self.images_popped_this_volume}/{self.images_expected_per_volume}"
                )
                img_array = self._process_tagged_image(tagged_img)
                if self.should_save_var.get():
                    self.current_volume_images.append(img_array)
                self.display_image(img_array)
            except Exception as e:
                print(f"Error popping image: {e}")
                self._finish_time_series()
                return
        if self.images_popped_this_volume >= self.images_expected_per_volume:
            self._finish_volume()
            return
        if (
            not mmc.isSequenceRunning(self.hw_interface.camera1)
            and mmc.getRemainingImageCount() == 0
        ):
            print("Warning: Sequence stopped unexpectedly.")
            self._finish_time_series()
            return
        self.root.after(20, self._poll_for_images)

    def _save_current_volume(self):
        if not self.should_save_var.get() or not self.current_volume_images:
            return
        save_dir = self.save_dir_var.get()
        prefix = self.save_prefix_var.get()
        if not save_dir or not prefix:
            self.status_var.set("Error: Save directory or prefix missing.")
            print("Error: Cannot save. Directory or prefix is missing.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_T{self.current_time_point:04d}_{timestamp}.tif"
        full_path = os.path.join(save_dir, filename)

        print(f"Saving volume to: {full_path}")
        self.status_var.set(f"Saving to {filename}...")

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
            print("Save complete.")
        except Exception as e:
            print(f"Error saving file with tifffile: {e}")
            self.status_var.set("Error: File save failed.")

    def _finish_volume(self):
        volume_duration = time.monotonic() - self.volume_start_time
        print(
            f"Volume {self.current_time_point} acquired in {volume_duration:.2f} seconds."
        )
        self._save_current_volume()
        _reset_for_next_volume()  # CORRECTED: Use the specific reset function
        if self.current_time_point >= self.time_points_total:
            self._finish_time_series()
        else:
            if self.minimal_interval_var.get():
                delay_s = 0
            else:
                user_interval_s = self.time_interval_s_var.get()
                delay_s = max(0, user_interval_s - volume_duration)
            self.status_var.set(f"Waiting {delay_s:.1f}s for next time point...")
            print(f"Waiting {delay_s:.2f} seconds before next volume.")
            self.root.after(int(delay_s * 1000), self._start_next_volume)

    def _finish_time_series(self, cancelled: bool = False):
        if cancelled:
            print("\n--- Acquisition Cancelled by User ---")
        else:
            print("\n--- Time Series Complete ---")
        final_cleanup(self.settings)  # This is the correct place for final_cleanup
        self.hw_interface.find_and_set_trigger_mode(
            self.hw_interface.camera1, ["Internal", "Internal Trigger"]
        )
        self.acquisition_in_progress = False
        self.run_button.grid()
        self.cancel_button.grid_remove()
        self.status_var.set("Ready" if not cancelled else "Cancelled")

    def _process_tagged_image(self, tagged_img) -> np.ndarray:
        height = int(tagged_img.tags.get("Height", 0))
        width = int(tagged_img.tags.get("Width", 0))
        return np.reshape(np.array(tagged_img.pix), (height, width))

    def display_image(self, img_array: np.ndarray):
        try:
            container = self.image_panel.master
            container_w = container.winfo_width()
            container_h = container.winfo_height()
            if container_w < 2 or container_h < 2:
                return
            img_min, img_max = np.min(img_array), np.max(img_array)
            if img_min == img_max:
                img_normalized = np.zeros_like(img_array, dtype=np.uint8)
            else:
                img_normalized = (
                    (img_array - img_min) / (img_max - img_min) * 255
                ).astype(np.uint8)
            pil_img = Image.fromarray(img_normalized)
            pil_img.thumbnail(
                (container_w, container_h),
                Image.Resampling.LANCZOS,
            )
            tk_img = ImageTk.PhotoImage(pil_img)
            self.image_panel.configure(image=tk_img)
            self._last_img = tk_img
        except Exception as e:
            if "pyimage" not in str(e):
                print(f"Error processing image for display: {e}")