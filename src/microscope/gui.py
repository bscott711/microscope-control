# gui.py
import os
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageTk
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMETiffWriter
from useq import MDAEvent, MDASequence, ZPlan  # CORRECTED: Import ZPlan

from .config import AcquisitionSettings
from .hardware_control import (
    HardwareInterface,
    _reset_for_next_volume,
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
        self.laser_duration_var = tk.DoubleVar(value=self.settings.laser_trig_duration_ms)
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
        self.pixel_size_um = 1.0

        self.create_widgets()
        self._bind_traces()
        self._update_all_estimates()
        self.control_widgets = []

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
        self._add_control_widget(
            ttk.Label(ts_frame, text="Time Points"),
            (0, 0),
            {"sticky": "w", "padx": 5, "pady": 2},
        )
        self._add_control_widget(
            ttk.Entry(ts_frame, textvariable=self.num_time_points_var),
            (0, 1),
            {"sticky": "ew", "padx": 5},
        )
        self._add_control_widget(
            ttk.Label(ts_frame, text="Interval (s)"),
            (1, 0),
            {"sticky": "w", "padx": 5, "pady": 2},
        )
        self._add_control_widget(
            ttk.Entry(ts_frame, textvariable=self.time_interval_s_var),
            (1, 1),
            {"sticky": "ew", "padx": 5},
        )
        self._add_control_widget(
            ttk.Checkbutton(ts_frame, text="Minimal Interval", variable=self.minimal_interval_var),
            (1, 2),
            {"sticky": "w", "padx": 5},
        )

        vol_frame = ttk.Labelframe(top_controls, text="Volume & Timing")
        vol_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        vol_frame.grid_columnconfigure(1, weight=1)
        self._add_control_widget(ttk.Label(vol_frame, text="Slices/Volume"), (0, 0), {"sticky": "w", "padx": 5})
        self._add_control_widget(
            ttk.Entry(vol_frame, textvariable=self.num_slices_var),
            (0, 1),
            {"sticky": "ew", "padx": 5},
        )
        self._add_control_widget(
            ttk.Label(vol_frame, text="Laser Duration (ms)"),
            (1, 0),
            {"sticky": "w", "padx": 5},
        )
        self._add_control_widget(
            ttk.Entry(vol_frame, textvariable=self.laser_duration_var),
            (1, 1),
            {"sticky": "ew", "padx": 5},
        )

        save_frame = ttk.Labelframe(main_frame, text="Data Saving")
        save_frame.grid(row=1, column=0, sticky="ew", pady=5)
        save_frame.grid_columnconfigure(1, weight=1)
        self._add_control_widget(
            ttk.Checkbutton(save_frame, text="Save to disk", variable=self.should_save_var),
            (0, 0),
            {"padx": 5},
        )
        dir_entry = ttk.Entry(save_frame, textvariable=self.save_dir_var, state="readonly")
        dir_entry.grid(row=0, column=1, sticky="ew", padx=5)
        self.control_widgets.append(dir_entry)
        browse_btn = ttk.Button(save_frame, text="Browse...", command=self._browse_save_directory)
        browse_btn.grid(row=0, column=2, padx=5)
        self.control_widgets.append(browse_btn)
        self._add_control_widget(ttk.Label(save_frame, text="File Prefix:"), (0, 3), {"padx": 5})
        self._add_control_widget(
            ttk.Entry(save_frame, textvariable=self.save_prefix_var),
            (0, 4),
            {"sticky": "ew", "padx": 5},
        )

        est_frame = ttk.Labelframe(main_frame, text="Estimates")
        est_frame.grid(row=2, column=0, sticky="ew", pady=5)
        # ... (rest of the GUI creation is the same)
        est_frame.grid_columnconfigure(1, weight=1)
        est_frame.grid_columnconfigure(3, weight=1)
        ttk.Label(est_frame, text="Camera Exposure:").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Label(est_frame, textvariable=self.camera_exposure_var).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(est_frame, text="Min. Interval/Volume:").grid(row=0, column=2, sticky="w", padx=5)
        ttk.Label(est_frame, textvariable=self.min_interval_display_var).grid(row=0, column=3, sticky="w", padx=5)
        ttk.Label(est_frame, text="Est. Total Time:").grid(row=1, column=2, sticky="w", padx=5)
        ttk.Label(est_frame, textvariable=self.total_time_display_var).grid(row=1, column=3, sticky="w", padx=5)

        display_frame = ttk.Frame(main_frame)
        display_frame.grid(row=3, column=0, sticky="nsew", pady=5)
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        self.image_panel = ttk.Label(display_frame, text="Camera Image", background="black", anchor="center")
        self.image_panel.grid(row=0, column=0, sticky="nsew")

        bottom_bar = ttk.Frame(main_frame)
        bottom_bar.grid(row=4, column=0, sticky="ew", pady=(5, 0))
        bottom_bar.grid_columnconfigure(1, weight=1)
        self.run_button = ttk.Button(bottom_bar, text="Run Time Series", command=self.start_time_series)
        self.run_button.grid(row=0, column=0, padx=5)
        self.cancel_button = ttk.Button(bottom_bar, text="Cancel", command=self._request_cancel, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=5)
        ttk.Label(bottom_bar, textvariable=self.status_var, anchor="w").grid(row=0, column=2, sticky="ew", padx=5)
        ttk.Button(bottom_bar, text="Exit", command=self.root.quit).grid(row=0, column=3, padx=5)

    def _add_control_widget(self, widget, grid_pos, grid_params):
        widget.grid(row=grid_pos[0], column=grid_pos[1], **grid_params)
        self.control_widgets.append(widget)

    def _set_controls_enabled(self, enabled: bool):
        for widget in self.control_widgets:
            try:
                widget.configure(state="normal" if enabled else "disabled")
            except tk.TclError:
                pass  # some widgets don't have a state

    def _browse_save_directory(self):
        directory = filedialog.askdirectory(title="Select Save Directory", initialdir=self.save_dir_var.get())
        if directory:
            self.save_dir_var.set(directory)

    def _bind_traces(self):
        for var in [
            self.num_time_points_var,
            self.time_interval_s_var,
            self.num_slices_var,
            self.laser_duration_var,
            self.minimal_interval_var,
        ]:
            var.trace_add("write", self._update_all_estimates)

    def _update_all_estimates(self, *args):
        try:
            self.settings.num_slices = self.num_slices_var.get()
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.settings.step_size_um = self.step_size_var.get()
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
        return (total_exposure_ms * overhead_factor) / 1000.0

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
        print("--- Cancel Requested by User ---")
        self.cancel_requested = True
        if self.acquisition_in_progress:
            mmc.mda.cancel()

    def start_time_series(self):
        if self.acquisition_in_progress:
            return

        self.acquisition_in_progress = True
        self.cancel_requested = False
        self._set_controls_enabled(False)
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")

        try:
            self.pixel_size_um = mmc.getPixelSizeUm() or 1.0
        except Exception:
            self.pixel_size_um = 1.0
            print("Warning: Could not get pixel size. Defaulting to 1.0 µm.")

        self._update_all_estimates()

        import threading

        thread = threading.Thread(target=self._run_mda_thread)
        thread.start()

    def _run_mda_thread(self):
        """Main acquisition loop, now using MDA."""
        time_points_total = self.num_time_points_var.get()

        mmc.setCameraDevice(self.hw_interface.camera1)

        for t_point in range(time_points_total):
            if self.cancel_requested:
                break

            volume_start_time = time.monotonic()
            self.status_var.set(f"Running Time Point {t_point + 1}/{time_points_total}")

            galvo_amp, galvo_center, num_slices = calculate_galvo_parameters(self.settings)

            # CORRECTED: Build the sequence explicitly.
            sequence = MDASequence()
            sequence.z_plan = ZPlan(steps=num_slices, step=self.settings.step_size_um)

            writer = None
            if self.should_save_var.get():
                save_dir = self.save_dir_var.get()
                prefix = self.save_prefix_var.get()
                if not save_dir or not prefix:
                    print("Error: Cannot save. Directory or prefix is missing.")
                    self._finish_time_series()
                    return

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{prefix}_T{t_point + 1:04d}_{timestamp}.tif"
                filepath = os.path.join(save_dir, filename)

                writer = OMETiffWriter(filepath)

            def _setup_plogic_for_volume(event: MDAEvent):
                if event.index.get("z", 0) == 0:
                    print("Configuring PLogic and triggering hardware Z-scan...")
                    configure_devices_for_slice_scan(self.settings, galvo_amp, galvo_center, num_slices)
                    mmc.setExposure(self.settings.camera_exposure_ms)
                    trigger_slice_scan_acquisition()

            def _on_frame_ready(image: np.ndarray, event: MDAEvent):
                self.display_image(image)
                z_index = event.index.get("z", 0)
                self.status_var.set(f"Time Point {t_point + 1}/{time_points_total} | Slice {z_index + 1}/{num_slices}")

            handlers = [_setup_plogic_for_volume, _on_frame_ready]
            if writer:
                handlers.append(writer)

            try:
                with mda_listeners_connected(*handlers):
                    mmc.run_mda(sequence)
            except RuntimeError as e:
                if "acquisition canceled" in str(e):
                    print("Acquisition gracefully cancelled.")
                else:
                    raise

            _reset_for_next_volume()

            if t_point < time_points_total - 1:
                volume_duration = time.monotonic() - volume_start_time
                if self.minimal_interval_var.get():
                    delay_s = 0
                else:
                    user_interval_s = self.time_interval_s_var.get()
                    delay_s = max(0, user_interval_s - volume_duration)

                self.status_var.set(f"Waiting {delay_s:.1f}s for next time point...")
                time.sleep(delay_s)

        self._finish_time_series()

    def _finish_time_series(self):
        final_cleanup(self.settings)
        self.hw_interface.find_and_set_trigger_mode(self.hw_interface.camera1, ["Internal", "Internal Trigger"])

        self.acquisition_in_progress = False
        self._set_controls_enabled(True)
        self.run_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Ready" if not self.cancel_requested else "Cancelled")

    def display_image(self, img_array: np.ndarray):
        try:
            container = self.image_panel.master
            container_w = container.winfo_width()
            container_h = container.winfo_height()
            if container_w < 2 or container_h < 2:
                self.root.after(50, lambda: self.display_image(img_array))
                return

            img_min, img_max = np.min(img_array), np.max(img_array)
            if img_min == img_max:
                img_normalized = np.zeros_like(img_array, dtype=np.uint8)
            else:
                img_normalized = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)

            pil_img = Image.fromarray(img_normalized)
            pil_img.thumbnail((container_w, container_h), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(pil_img)
            self.image_panel.configure(image=tk_img)
            self._last_img = tk_img
        except Exception as e:
            if "pyimage" not in str(e):
                print(f"Error processing image for display: {e}")
