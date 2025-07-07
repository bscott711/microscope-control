import os
import time
import tkinter as tk
import traceback
from dataclasses import dataclass
from datetime import datetime
from tkinter import filedialog, ttk
from typing import Optional

import numpy as np
import tifffile
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
    laser_trig_duration_ms: float = 10.0
    camera_exposure_ms: float = 10.0


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
    plogic_trigger_ttl_addr: int = 41
    plogic_4khz_clock_addr: int = 192
    plogic_laser_on_cell: int = 10
    plogic_camera_cell: int = 11
    pulses_per_ms: float = 4.0
    # Laser Preset Configuration
    plogic_laser_preset_num: int = 30
    # Calibration
    slice_calibration_slope_um_per_deg: float = 100.0
    # Timing Parameters
    delay_before_scan_ms: float = 0.0
    line_scans_per_slice: int = 1
    line_scan_duration_ms: float = 1.0
    delay_before_side_ms: float = 0.0


# Instantiate constants
HW = HardwareConstants()


# --- Low-Level Helper Functions ---
def set_property(device_label: str, property_name: str, value):
    """Sets a Micro-Manager device property if it has changed."""
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        if mmc.getProperty(device_label, property_name) != str(value):
            mmc.setProperty(device_label, property_name, value)
    else:
        print(f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found.")


def get_property(device_label: str, property_name: str) -> str | None:
    """
    Safely gets a Micro-Manager device property value.

    Args:
        device_label: The label of the device in Micro-Manager.
        property_name: The name of the property to retrieve.

    Returns:
        The property value as a string if found, otherwise None.
    """
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        return mmc.getProperty(device_label, property_name)

    print(f"Warning: Cannot get '{property_name}' for device '{device_label}'. Device or property not found.")
    return None


def configure_plogic_for_dual_nrt_pulses(settings: AcquisitionSettings):
    """
    Configures PLogic to generate two independent, synchronized NRT one-shot pulses.
    This version sends all serial commands in a single, efficient batch.

    There are 4 main steps:
    1. Move the axis position to the cell.
    2. Select the type of cell.
    3. Set the cell configuration parameters.
    4. Set the cell inputs.

    An example command sequence to configure cell 10 for a One Shot NRT pulse off the Tiger
    Backplane TTL0 and clocked by the 4kHz Tiger Clock:
    ```
    M E=10                  # Move to cell 10
    CCA Y=14                # Set cell type to NRT One-Shot
    CCA Z=40                # Set duration to 40 cycles (10ms)
    CCB X=41 Y=128          # Set inputs: TTL41 (Tiger Comm Hub TTL0) and 4kHz clock
    ```
    """

    plogic_addr_prefix = HW.plogic_label.split(":")[-1]
    hub_label = HW.tiger_comm_hub_label
    hub_prop = "OnlySendSerialCommandOnChange"
    original_hub_setting = mmc.getProperty(hub_label, hub_prop)

    def _send(cmd: str):
        """Internal helper to send a command and sleep."""
        mmc.setProperty(hub_label, "SerialCommand", cmd)
        time.sleep(0.01)  # Short sleep to allow command processing

    try:
        # Set hub to send all commands regardless of change
        if original_hub_setting == "Yes":
            mmc.setProperty(hub_label, hub_prop, "No")

        # --- Batch PLogic Configuration ---
        # 0. Reset PLogic
        _send(f"{plogic_addr_prefix}CCA X=0")  # Reset all cells

        # 1. Program Laser Preset and Laser Indicator
        _send(f"{plogic_addr_prefix}CCA X={HW.plogic_laser_preset_num}")
        _send(f"{plogic_addr_prefix}CCA X=27")  # This will turn on the laser indicator (BNC3)
        print(f"Laser preset number: {HW.plogic_laser_preset_num}")

        # 2. Program Camera Pulse (NRT One-Shot #1)
        _send(f"M E={HW.plogic_camera_cell}")  # Point to Camera Cell, 11
        _send(f"{plogic_addr_prefix}CCA Y=14")  # Type: NRT one-shot
        camera_pulse_cycles = int(settings.camera_exposure_ms * HW.pulses_per_ms)
        _send(f"{plogic_addr_prefix}CCA Z={camera_pulse_cycles}")  # Set duration
        clock_source = HW.plogic_4khz_clock_addr
        trigger = HW.plogic_trigger_ttl_addr
        _send(f"{plogic_addr_prefix}CCB X={trigger} Y={clock_source} Z=0")

        # 3. Program Laser Pulse (NRT One-Shot #2)
        _send(f"M E={HW.plogic_laser_on_cell}")
        _send(f"{plogic_addr_prefix}CCA Y=14")  # Type: NRT one-shot
        laser_pulse_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
        _send(f"{plogic_addr_prefix}CCA Z={laser_pulse_cycles}")  # Set duration
        _send(f"{plogic_addr_prefix}CCB X={trigger} Y={clock_source} Z=0")

        # 4. Route Cell Outputs to BNCs
        _send("M E=33")  # Point to BNC1
        _send(f"{plogic_addr_prefix}CCA Z={HW.plogic_camera_cell}")

        # 5. Save the configuration
        _send(f"{plogic_addr_prefix}SS Z")  # Save configuration to non-volatile memory
        print("PLogic configured for dual NRT pulses successfully.")

    finally:
        # IMPORTANT: Always restore the original hub setting
        if original_hub_setting == "Yes":
            mmc.setProperty(hub_label, hub_prop, "Yes")


def calculate_galvo_parameters(settings: AcquisitionSettings):
    """Converts the slice from um to degrees using the galvo calibration slope."""
    if abs(HW.slice_calibration_slope_um_per_deg) < 1e-9:
        raise ValueError("Slice calibration slope cannot be zero.")
    num_slices_ctrl = settings.num_slices
    amplitude_um = (num_slices_ctrl - 1) * settings.step_size_um
    galvo_slice_amplitude_deg = amplitude_um / HW.slice_calibration_slope_um_per_deg
    return (
        round(galvo_slice_amplitude_deg, 4),
        num_slices_ctrl,
    )


def configure_devices_for_slice_scan(
    galvo_amplitude_deg: float,
    num_slices_ctrl: int,
):
    """Configures galvo and piezo for a single volume scan."""
    print("DEBUG: Configuring devices for new volume scan...")

    set_property(HW.galvo_a_label, "BeamEnabled", "Yes")

    # PLogic configuration is now done only once at the start of the time-series.
    # Setting galvo properties for the scan:
    set_property(HW.galvo_a_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
    set_property(HW.galvo_a_label, "SPIMNumRepeats", 1)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
    set_property(HW.galvo_a_label, "SPIMAlternateDirectionsEnable", "No")
    set_property(HW.galvo_a_label, "SPIMScanDuration(ms)", HW.line_scan_duration_ms)
    set_property(HW.galvo_a_label, "SingleAxisYAmplitude(deg)", galvo_amplitude_deg)
    set_property(HW.galvo_a_label, "SingleAxisYOffset(deg)", 0)
    set_property(HW.galvo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.galvo_a_label, "SPIMNumSides", 1)
    set_property(HW.galvo_a_label, "SPIMFirstSide", "A")
    set_property(HW.galvo_a_label, "SPIMPiezoHomeDisable", "No")
    set_property(HW.galvo_a_label, "SPIMInterleaveSidesEnable", "No")
    set_property(HW.galvo_a_label, "SingleAxisXAmplitude(deg)", 0)
    set_property(HW.galvo_a_label, "SingleAxisXOffset(deg)", 0)
    print("DEBUG: All device properties set for this volume.")


def trigger_slice_scan_acquisition():
    set_property(HW.galvo_a_label, "SPIMState", "Running")
    print("=== Running SPIMState ===")
    print(f"{HW.galvo_a_label} SPIMState: {get_property(HW.galvo_a_label, 'SPIMState')}")


def _reset_for_next_volume():
    print("Resetting controller state for next volume...")
    set_property(HW.galvo_a_label, "BeamEnabled", "No")
    set_property(HW.galvo_a_label, "SPIMState", "Idle")


def final_cleanup():
    print("Performing final cleanup...")
    _reset_for_next_volume()


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
            raise FileNotFoundError("HardwareInterface requires a config_path, and no valid ASI config is loaded.")
        if not os.path.isabs(target_config):
            target_config = os.path.abspath(target_config)
        if os.path.normcase(current_config) == os.path.normcase(target_config):
            print(f"Target configuration '{target_config}' is already loaded.")
            return
        print(f"Attempting to load configuration: '{target_config}'")
        try:
            mmc.loadSystemConfiguration(target_config)
            if HW.tiger_comm_hub_label not in mmc.getLoadedDevices():
                raise RuntimeError("Loaded config does not appear to contain an ASI TigerCommHub.")
            print(f"Successfully loaded: {mmc.systemConfigurationFile()}")
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{target_config}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        return HW.camera_a_label

    def find_and_set_trigger_mode(self, camera_label: str, desired_modes: list[str]) -> bool:
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
        self.root.title("ASI OPM Acquisition Control")

        # GUI Variables
        self.num_slices_var = tk.IntVar(value=self.settings.num_slices)
        self.step_size_var = tk.DoubleVar(value=self.settings.step_size_um)
        self.laser_duration_var = tk.DoubleVar(value=self.settings.laser_trig_duration_ms)
        self.camera_exposure_var = tk.DoubleVar(value=self.settings.camera_exposure_ms)
        self.num_time_points_var = tk.IntVar(value=1)
        self.time_interval_s_var = tk.DoubleVar(value=10.0)
        self.minimal_interval_var = tk.BooleanVar(value=False)
        self.should_save_var = tk.BooleanVar(value=False)
        self.save_dir_var = tk.StringVar()
        self.save_prefix_var = tk.StringVar(value="acquisition")

        # Display Variables
        self.camera_exposure_display_var = tk.StringVar()
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
        self.current_volume_images = []
        self.pixel_size_um = 0.128

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
        ttk.Label(ts_frame, text="Time Points").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(ts_frame, textvariable=self.num_time_points_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(ts_frame, text="Interval (s)").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        ttk.Entry(ts_frame, textvariable=self.time_interval_s_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Checkbutton(ts_frame, text="Minimal Interval", variable=self.minimal_interval_var).grid(
            row=1, column=2, sticky="w", padx=5
        )

        vol_frame = ttk.Labelframe(top_controls, text="Volume & Timing")
        vol_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        vol_frame.grid_columnconfigure(1, weight=1)
        ttk.Label(vol_frame, text="Slices/Volume").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Entry(vol_frame, textvariable=self.num_slices_var).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(vol_frame, text="Camera Exposure (ms)").grid(row=1, column=0, sticky="w", padx=5)
        ttk.Entry(vol_frame, textvariable=self.camera_exposure_var).grid(row=1, column=1, sticky="ew", padx=5)
        ttk.Label(vol_frame, text="Laser Duration (ms)").grid(row=2, column=0, sticky="w", padx=5)
        ttk.Entry(vol_frame, textvariable=self.laser_duration_var).grid(row=2, column=1, sticky="ew", padx=5)

        save_frame = ttk.Labelframe(main_frame, text="Data Saving")
        save_frame.grid(row=1, column=0, sticky="ew", pady=5)
        save_frame.grid_columnconfigure(1, weight=1)
        ttk.Checkbutton(save_frame, text="Save to disk", variable=self.should_save_var).grid(row=0, column=0, padx=5)
        dir_entry = ttk.Entry(save_frame, textvariable=self.save_dir_var, state="readonly")
        dir_entry.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(save_frame, text="Browse...", command=self._browse_save_directory).grid(row=0, column=2, padx=5)
        ttk.Label(save_frame, text="File Prefix:").grid(row=0, column=3, padx=5)
        ttk.Entry(save_frame, textvariable=self.save_prefix_var).grid(row=0, column=4, sticky="ew", padx=5)

        est_frame = ttk.Labelframe(main_frame, text="Estimates")
        est_frame.grid(row=2, column=0, sticky="ew", pady=5)
        est_frame.grid_columnconfigure(1, weight=1)
        est_frame.grid_columnconfigure(3, weight=1)
        ttk.Label(est_frame, text="Camera Exposure:").grid(row=0, column=0, sticky="w", padx=5)
        ttk.Label(est_frame, textvariable=self.camera_exposure_display_var).grid(row=0, column=1, sticky="w", padx=5)
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
        self.cancel_button = ttk.Button(bottom_bar, text="Cancel", command=self._request_cancel)
        self.cancel_button.grid(row=0, column=0, padx=5)
        self.cancel_button.grid_remove()
        ttk.Label(bottom_bar, textvariable=self.status_var, anchor="w").grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(bottom_bar, text="Exit", command=self.root.quit).grid(row=0, column=2, padx=5)

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
            self.camera_exposure_var,
        ]:
            var.trace_add("write", self._update_all_estimates)
        self.minimal_interval_var.trace_add("write", self._update_all_estimates)

    def _update_all_estimates(self, *args):
        try:
            self.settings.num_slices = self.num_slices_var.get()
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.settings.camera_exposure_ms = self.camera_exposure_var.get()

            self.camera_exposure_display_var.set(f"{self.settings.camera_exposure_ms:.2f} ms")
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

        try:
            self.settings.num_slices = self.num_slices_var.get()
            self.settings.step_size_um = self.step_size_var.get()
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.settings.camera_exposure_ms = self.camera_exposure_var.get()
            self.time_points_total = self.num_time_points_var.get()
        except (tk.TclError, ValueError):
            self.status_var.set("Error: Invalid value in one of the input fields.")
            print("Could not start acquisition due to an invalid numerical input.")
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
            self.pixel_size_um = 0.128
            print("Warning: Could not get pixel size. Defaulting to 0.128 µm.")

        # Configure the PLogic card ONCE at the beginning of the whole series.
        print("\n--- Performing One-Time PLogic Configuration ---")
        configure_plogic_for_dual_nrt_pulses(self.settings)
        print("--- PLogic Configuration Complete ---")

        self.current_time_point = 0
        self._update_all_estimates()
        print("\n--- Starting Time Series Loop ---")
        self._start_next_volume()

    def _start_next_volume(self):
        self.current_time_point += 1
        self.current_volume_images.clear()
        self.status_var.set(f"Starting Time Point {self.current_time_point}/{self.time_points_total}...")
        print(f"\nStarting Volume {self.current_time_point}/{self.time_points_total}")
        try:
            (
                galvo_amp,
                self.images_expected_per_volume,
            ) = calculate_galvo_parameters(self.settings)
            mmc.setCameraDevice(self.hw_interface.camera1)
            if not self.hw_interface.find_and_set_trigger_mode(
                self.hw_interface.camera1, ["Level Trigger", "Edge Trigger"]
            ):
                raise RuntimeError("Failed to set external trigger mode.")
            configure_devices_for_slice_scan(
                galvo_amp,
                self.images_expected_per_volume,
            )
            mmc.setExposure(self.hw_interface.camera1, self.settings.camera_exposure_ms)
            mmc.initializeCircularBuffer()
            mmc.startSequenceAcquisition(self.hw_interface.camera1, self.images_expected_per_volume, 0, True)
            self.volume_start_time = time.monotonic()
            trigger_slice_scan_acquisition()
            self.images_popped_this_volume = 0
            self.root.after(100, self._poll_for_images)
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
        if not mmc.isSequenceRunning(self.hw_interface.camera1) and mmc.getRemainingImageCount() == 0:
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
        print(f"Volume {self.current_time_point} acquired in {volume_duration:.2f} seconds.")
        self._save_current_volume()
        _reset_for_next_volume()
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
        final_cleanup()
        self.hw_interface.find_and_set_trigger_mode(self.hw_interface.camera1, ["Internal Trigger"])
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
                img_normalized = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)
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
