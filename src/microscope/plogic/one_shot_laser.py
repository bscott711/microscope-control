import os
import time
import traceback
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import List, Optional

import numpy as np
from PIL import Image, ImageTk
from pymmcore_plus import CMMCorePlus

# Initialize global core instance
mmc = CMMCorePlus.instance()


# --- Global Constants and Configuration ---
@dataclass
class AcquisitionSettings:
    """Stores all user-configurable acquisition parameters."""

    num_slices: int = 3
    step_size_um: float = 1.0
    piezo_center_um: float = -31.0
    laser_trig_duration_ms: float = 10.0
    delay_before_camera_ms: float = 18.0

    @property
    def camera_exposure_ms(self) -> float:
        """Derived camera exposure time."""
        return self.laser_trig_duration_ms + 1.95

    @property
    def delay_before_laser_ms(self) -> float:
        """Derived laser delay time."""
        return self.delay_before_camera_ms + 1.25


@dataclass
class HardwareConstants:
    """Stores fixed hardware configuration and constants."""

    cfg_path: str = "hardware_profiles/20250523-OPM.cfg"
    # Device labels
    galvo_a_label: str = "Scanner:AB:33"
    piezo_a_label: str = "PiezoStage:P:34"
    camera_a_label: str = "Camera-1"
    plogic_label: str = "PLogic:E:36"
    tiger_comm_hub_label: str = "TigerCommHub"
    # PLogic addresses and presets
    plogic_camera_trigger_ttl_addr: int = 44
    plogic_laser_trigger_ttl_addr: int = 45
    plogic_galvo_trigger_ttl_addr: int = 43
    plogic_4khz_clock_addr: int = 192
    plogic_laser_on_cell: int = 10
    plogic_laser_preset_num: int = 5
    plogic_delay_before_laser_cell: int = 11
    plogic_delay_before_camera_cell: int = 12
    pulses_per_ms: float = 4.0
    # Calibration
    slice_calibration_slope_um_per_deg: float = 100.0
    slice_calibration_offset_um: float = 0.0
    # Timing Parameters
    delay_before_scan_ms: float = 0.0
    line_scans_per_slice: int = 1
    line_scan_duration_ms: float = 1.0
    num_sides: int = 1
    first_side_is_a: bool = True
    scan_opposite_directions: bool = False
    sheet_width_deg: float = 0.5
    sheet_offset_deg: float = 0.0
    delay_before_side_ms: float = 0.0
    camera_mode_is_overlap: bool = False


# Instantiate constants
HW = HardwareConstants()


# --- Low-Level Helper Functions ---
def _execute_tiger_serial_command(command_string: str):
    original_setting = mmc.getProperty(
        HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "No")
    mmc.setProperty(HW.tiger_comm_hub_label, "SerialCommand", command_string)
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "Yes")
    time.sleep(0.02)


def set_property(device_label: str, property_name: str, value):
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        if mmc.getProperty(device_label, property_name) != str(value):
            mmc.setProperty(device_label, property_name, value)
    else:
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. "
            "Device or property not found."
        )


def configure_plogic_for_one_shot_laser(settings: AcquisitionSettings):
    plogic_addr = HW.plogic_label[-2:]
    _execute_tiger_serial_command(f"{plogic_addr}CCA X={HW.plogic_laser_preset_num}")
    _execute_tiger_serial_command(f"M E={HW.plogic_laser_on_cell}")
    _execute_tiger_serial_command("CCA Y=14")
    pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_camera_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_laser_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_camera_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )


def calculate_galvo_parameters(settings: AcquisitionSettings):
    if abs(HW.slice_calibration_slope_um_per_deg) < 1e-9:
        raise ValueError("Slice calibration slope cannot be zero.")
    num_slices_ctrl = settings.num_slices
    piezo_amplitude_um = (num_slices_ctrl - 1) * settings.step_size_um
    if HW.camera_mode_is_overlap:
        if num_slices_ctrl > 1:
            piezo_amplitude_um *= float(num_slices_ctrl) / (num_slices_ctrl - 1.0)
        num_slices_ctrl += 1
    galvo_slice_amplitude_deg = (
        piezo_amplitude_um / HW.slice_calibration_slope_um_per_deg
    )
    galvo_slice_center_deg = (
        settings.piezo_center_um - HW.slice_calibration_offset_um
    ) / HW.slice_calibration_slope_um_per_deg
    return (
        round(galvo_slice_amplitude_deg, 4),
        round(galvo_slice_center_deg, 4),
        num_slices_ctrl,
    )


def configure_devices_for_slice_scan(
    settings: AcquisitionSettings,
    galvo_amplitude_deg: float,
    galvo_center_deg: float,
    num_slices_ctrl: int,
):
    piezo_fixed_pos_um = round(settings.piezo_center_um, 3)
    set_property(HW.galvo_a_label, "BeamEnabled", "Yes")
    configure_plogic_for_one_shot_laser(settings)
    set_property(HW.galvo_a_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
    set_property(HW.galvo_a_label, "SPIMNumRepeats", 1)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
    set_property(
        HW.galvo_a_label,
        "SPIMAlternateDirectionsEnable",
        "Yes" if HW.scan_opposite_directions else "No",
    )
    set_property(HW.galvo_a_label, "SPIMScanDuration(ms)", HW.line_scan_duration_ms)
    set_property(HW.galvo_a_label, "SingleAxisYAmplitude(deg)", galvo_amplitude_deg)
    set_property(HW.galvo_a_label, "SingleAxisYOffset(deg)", galvo_center_deg)
    set_property(HW.galvo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.galvo_a_label, "SPIMNumSides", HW.num_sides)
    set_property(HW.galvo_a_label, "SPIMFirstSide", "A" if HW.first_side_is_a else "B")
    set_property(HW.galvo_a_label, "SPIMPiezoHomeDisable", "No")
    set_property(HW.galvo_a_label, "SPIMInterleaveSidesEnable", "No")
    set_property(HW.galvo_a_label, "SingleAxisXAmplitude(deg)", HW.sheet_width_deg)
    set_property(HW.galvo_a_label, "SingleAxisXOffset(deg)", HW.sheet_offset_deg)
    set_property(HW.piezo_a_label, "SingleAxisAmplitude(um)", 0.0)
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", piezo_fixed_pos_um)
    set_property(HW.piezo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.piezo_a_label, "SPIMState", "Armed")


def trigger_slice_scan_acquisition():
    set_property(HW.galvo_a_label, "SPIMState", "Running")


def _reset_for_next_volume():
    print("Resetting controller state for next volume...")
    set_property(HW.galvo_a_label, "BeamEnabled", "No")
    set_property(HW.galvo_a_label, "SPIMState", "Idle")
    set_property(HW.piezo_a_label, "SPIMState", "Idle")


def final_cleanup(settings: AcquisitionSettings):
    print("Performing final cleanup...")
    _reset_for_next_volume()
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)


# --- HardwareInterface Class ---
class HardwareInterface:
    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        print("Initializing HardwareInterface...")
        current_config = mmc.systemConfigurationFile() or ""
        target_config = self.config_path
        if not target_config:
            if HW.tiger_comm_hub_label in mmc.getLoadedDevices():
                print(f"Using existing MMCore config: {current_config}")
                return
            raise FileNotFoundError(
                "HardwareInterface requires a config_path, and no valid ASI "
                "config is loaded."
            )
        if not os.path.isabs(target_config):
            target_config = os.path.abspath(target_config)
        if os.path.normcase(current_config) == os.path.normcase(target_config):
            print(f"Target configuration '{target_config}' is already loaded.")
            return
        print(f"Attempting to load configuration: '{target_config}'")
        try:
            mmc.loadSystemConfiguration(target_config)
            if HW.tiger_comm_hub_label not in mmc.getLoadedDevices():
                raise RuntimeError(
                    "Loaded config does not appear to contain an ASI TigerCommHub."
                )
            print(f"Successfully loaded: {mmc.systemConfigurationFile()}")
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{target_config}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        return HW.camera_a_label

    def find_and_set_trigger_mode(
        self, camera_label: str, desired_modes: List[str]
    ) -> bool:
        if camera_label not in mmc.getLoadedDevices():
            return False
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            return False
        try:
            allowed = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
            for mode in desired_modes:
                if mode in allowed:
                    set_property(camera_label, trigger_prop, mode)
                    return True
            return False
        except Exception:
            return False


# --- Tkinter GUI with Live Image Display ---
class AcquisitionGUI:
    def __init__(self, root: tk.Tk, hw_interface: HardwareInterface):
        self.root = root
        self.hw_interface = hw_interface
        self.settings = AcquisitionSettings()
        self.root.title("ASI SPIM Acquisition Control")

        # GUI Variables
        self.num_slices_var = tk.IntVar(value=self.settings.num_slices)
        self.step_size_var = tk.DoubleVar(value=self.settings.step_size_um)
        self.laser_duration_var = tk.DoubleVar(
            value=self.settings.laser_trig_duration_ms
        )
        self.delay_before_camera_var = tk.DoubleVar(
            value=self.settings.delay_before_camera_ms
        )
        self.num_time_points_var = tk.IntVar(value=1)
        self.time_interval_s_var = tk.DoubleVar(value=10.0)
        self.minimal_interval_var = tk.BooleanVar(value=False)

        # Display Variables
        self.camera_exposure_var = tk.StringVar()
        self.delay_before_laser_var = tk.StringVar()
        self.min_interval_display_var = tk.StringVar()
        self.total_time_display_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready")
        self._last_img = None

        # Acquisition State
        self.acquisition_in_progress = False
        self.time_points_total = 0
        self.current_time_point = 0
        self.images_expected_per_volume = 0
        self.images_popped_this_volume = 0
        self.volume_start_time = 0.0

        self.create_widgets()
        self._bind_traces()
        self._update_all_estimates()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # --- Top Controls ---
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
        ttk.Label(vol_frame, text="Step Size (µm)").grid(
            row=1, column=0, sticky="w", padx=5
        )
        ttk.Entry(vol_frame, textvariable=self.step_size_var).grid(
            row=1, column=1, sticky="ew", padx=5
        )
        ttk.Label(vol_frame, text="Laser Duration (ms)").grid(
            row=2, column=0, sticky="w", padx=5
        )
        ttk.Entry(vol_frame, textvariable=self.laser_duration_var).grid(
            row=2, column=1, sticky="ew", padx=5
        )
        ttk.Label(vol_frame, text="Delay Before Camera (ms)").grid(
            row=3, column=0, sticky="w", padx=5
        )
        ttk.Entry(vol_frame, textvariable=self.delay_before_camera_var).grid(
            row=3, column=1, sticky="ew", padx=5
        )

        # --- Estimates ---
        est_frame = ttk.Labelframe(main_frame, text="Estimates")
        est_frame.grid(row=1, column=0, sticky="ew", pady=5)
        est_frame.grid_columnconfigure(1, weight=1)
        est_frame.grid_columnconfigure(3, weight=1)
        ttk.Label(est_frame, text="Camera Exposure:").grid(
            row=0, column=0, sticky="w", padx=5
        )
        ttk.Label(est_frame, textvariable=self.camera_exposure_var).grid(
            row=0, column=1, sticky="w", padx=5
        )
        ttk.Label(est_frame, text="Delay Before Laser:").grid(
            row=1, column=0, sticky="w", padx=5
        )
        ttk.Label(est_frame, textvariable=self.delay_before_laser_var).grid(
            row=1, column=1, sticky="w", padx=5
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

        # --- Image Display ---
        display_frame = ttk.Frame(main_frame)
        display_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        self.image_panel = ttk.Label(
            display_frame, text="Camera Image", background="black", anchor="center"
        )
        self.image_panel.grid(row=0, column=0, sticky="nsew")

        # --- Bottom Bar ---
        bottom_bar = ttk.Frame(main_frame)
        bottom_bar.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        bottom_bar.grid_columnconfigure(1, weight=1)
        self.run_button = ttk.Button(
            bottom_bar, text="Run Time Series", command=self.start_time_series
        )
        self.run_button.grid(row=0, column=0, padx=5)
        ttk.Label(bottom_bar, textvariable=self.status_var, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Button(bottom_bar, text="Exit", command=self.root.quit).grid(
            row=0, column=2, padx=5
        )

    def _bind_traces(self):
        """Link GUI variable changes to the update function."""
        for var in [
            self.num_time_points_var,
            self.time_interval_s_var,
            self.num_slices_var,
            self.laser_duration_var,
            self.delay_before_camera_var,
        ]:
            var.trace_add("write", self._update_all_estimates)
        self.minimal_interval_var.trace_add("write", self._update_all_estimates)

    def _update_all_estimates(self, *args):
        """Master function to update all calculated values and estimates."""
        try:
            # Update settings object from GUI
            self.settings.num_slices = self.num_slices_var.get()
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.settings.delay_before_camera_ms = self.delay_before_camera_var.get()

            # Update derived timing displays
            self.camera_exposure_var.set(f"{self.settings.camera_exposure_ms:.2f} ms")
            self.delay_before_laser_var.set(
                f"{self.settings.delay_before_laser_ms:.2f} ms"
            )

            # Calculate and display minimal interval
            min_interval_s = self._calculate_minimal_interval()
            self.min_interval_display_var.set(f"{min_interval_s:.2f} s")

            # Calculate and display total time
            total_time_str = self._calculate_total_time(min_interval_s)
            self.total_time_display_var.set(total_time_str)

        except (tk.TclError, ValueError):
            # Handles cases where an entry is empty or contains invalid text
            return

    def _calculate_minimal_interval(self) -> float:
        """Estimate the minimum time to acquire one volume."""
        # A simple estimation based on camera exposure + a small overhead
        # for readout and galvo movement. A 10% overhead is a reasonable guess.
        overhead_factor = 1.10
        total_exposure_ms = self.settings.num_slices * self.settings.camera_exposure_ms
        estimated_ms = total_exposure_ms * overhead_factor
        return estimated_ms / 1000.0

    def _calculate_total_time(self, min_interval_s: float) -> str:
        """Estimate the total time for the entire time series."""
        num_time_points = self.num_time_points_var.get()
        if self.minimal_interval_var.get():
            time_per_volume_s = min_interval_s
        else:
            user_interval_s = self.time_interval_s_var.get()
            time_per_volume_s = max(user_interval_s, min_interval_s)

        total_seconds = time_per_volume_s * num_time_points

        # Format into HH:MM:SS
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = int(total_seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def start_time_series(self):
        if self.acquisition_in_progress:
            return
        self.acquisition_in_progress = True
        self.run_button.configure(state="disabled")
        self.status_var.set("Initializing...")
        self.settings.step_size_um = self.step_size_var.get()
        self.time_points_total = self.num_time_points_var.get()
        self.current_time_point = 0
        self._update_all_estimates()
        print("\n--- Starting Time Series ---")
        self._start_next_volume()

    def _start_next_volume(self):
        self.current_time_point += 1
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

    def _finish_volume(self):
        volume_duration = time.monotonic() - self.volume_start_time
        print(
            f"Volume {self.current_time_point} acquired in {volume_duration:.2f} seconds."
        )
        _reset_for_next_volume()
        if self.current_time_point >= self.time_points_total:
            self._finish_time_series()
        else:
            min_interval_s = self._calculate_minimal_interval()
            if self.minimal_interval_var.get():
                delay_s = 0
            else:
                user_interval_s = self.time_interval_s_var.get()
                delay_s = max(0, user_interval_s - volume_duration)
            self.status_var.set(f"Waiting {delay_s:.1f}s for next time point...")
            print(f"Waiting {delay_s:.2f} seconds before next volume.")
            self.root.after(int(delay_s * 1000), self._start_next_volume)

    def _finish_time_series(self):
        print("\n--- Time Series Complete ---")
        final_cleanup(self.settings)
        self.hw_interface.find_and_set_trigger_mode(
            self.hw_interface.camera1, ["Internal", "Internal Trigger"]
        )
        self.acquisition_in_progress = False
        self.run_button.configure(state="normal")
        self.status_var.set("Ready")

    def _process_tagged_image(self, tagged_img) -> np.ndarray:
        height = int(tagged_img.tags.get("Height", 0))
        width = int(tagged_img.tags.get("Width", 0))
        return np.reshape(np.array(tagged_img.pix), (height, width))

    def display_image(self, img_array: np.ndarray):
        try:
            img_min, img_max = np.min(img_array), np.max(img_array)
            if img_min == img_max:
                img_normalized = np.zeros_like(img_array, dtype=np.uint8)
            else:
                img_normalized = (
                    (img_array - img_min) / (img_max - img_min) * 255
                ).astype(np.uint8)
            pil_img = Image.fromarray(img_normalized)
            pil_img.thumbnail(
                (
                    self.image_panel.winfo_width(),
                    self.image_panel.winfo_height(),
                ),
                Image.Resampling.LANCZOS,
            )
            tk_img = ImageTk.PhotoImage(pil_img)
            self.image_panel.configure(image=tk_img)
            self._last_img = tk_img
        except Exception as e:
            if "pyimage" not in str(e):
                print(f"Error processing image for display: {e}")


if __name__ == "__main__":
    try:
        hw_main_interface = HardwareInterface(config_file_path=HW.cfg_path)
        root = tk.Tk()
        root.minsize(600, 700)
        app = AcquisitionGUI(root, hw_main_interface)
        root.mainloop()
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        if "mmc" in locals() and mmc.getLoadedDevices():
            mmc.reset()
        print("Script execution finished.")
