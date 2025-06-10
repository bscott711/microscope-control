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
    laser_trig_duration_ms: float = 10.0  # Effective sample exposure
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
    """Send a serial command to the Tiger controller, bypassing the send-on-change lock."""
    original_setting = mmc.getProperty(
        HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "No")

    mmc.setProperty(HW.tiger_comm_hub_label, "SerialCommand", command_string)

    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "Yes")
    time.sleep(0.02)  # Give controller time to process


def set_property(device_label: str, property_name: str, value):
    """Set a device property if the device exists and the value is different."""
    if device_label not in mmc.getLoadedDevices() or not mmc.hasProperty(
        device_label, property_name
    ):
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. "
            "Device or property not found."
        )
        return

    if mmc.getProperty(device_label, property_name) != str(value):
        mmc.setProperty(device_label, property_name, value)


def configure_plogic_for_one_shot_laser(settings: AcquisitionSettings):
    """Program the PLogic card for timed laser and camera trigger pulses."""
    plogic_addr = HW.plogic_label[-2:]
    # Configure laser pulse duration
    _execute_tiger_serial_command(f"{plogic_addr}CCA X={HW.plogic_laser_preset_num}")
    _execute_tiger_serial_command(f"M E={HW.plogic_laser_on_cell}")
    _execute_tiger_serial_command("CCA Y=14")
    pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_camera_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    # Configure delay before laser
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_laser_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    # Configure delay before camera
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_camera_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )


def calculate_galvo_parameters(settings: AcquisitionSettings):
    """Calculate galvo amplitude and center based on slice settings."""
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
    """Configure Galvo, Piezo, and PLogic for a single volume scan."""
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
    """Trigger the armed SPIM state."""
    set_property(HW.galvo_a_label, "SPIMState", "Running")


def _reset_for_next_volume():
    """Reset the controller to an idle state, ready for the next volume."""
    print("Resetting controller state for next volume...")
    set_property(HW.galvo_a_label, "BeamEnabled", "No")
    set_property(HW.galvo_a_label, "SPIMState", "Idle")
    set_property(HW.piezo_a_label, "SPIMState", "Idle")


def final_cleanup(settings: AcquisitionSettings):
    """Return all devices to a safe, final idle state."""
    print("Performing final cleanup...")
    _reset_for_next_volume()
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)


# --- HardwareInterface Class ---
class HardwareInterface:
    """Manages hardware initialization and connection."""

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
            print(f"Error: Camera device '{camera_label}' not found.")
            return False
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            print(f"Error: Camera '{camera_label}' lacks property '{trigger_prop}'.")
            return False
        try:
            allowed = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
            for mode in desired_modes:
                if mode in allowed:
                    set_property(camera_label, trigger_prop, mode)
                    return True
            print(
                f"Error: None of desired modes {desired_modes} available. "
                f"Allowed: {allowed}"
            )
            return False
        except Exception as e:
            print(f"Error setting trigger mode for {camera_label}: {e}")
            return False


# --- Tkinter GUI with Live Image Display ---
class AcquisitionGUI:
    """Manages the Tkinter GUI for acquisition control and live display."""

    def __init__(self, root: tk.Tk, hw_interface: HardwareInterface):
        self.root = root
        self.hw_interface = hw_interface
        self.settings = AcquisitionSettings()
        self.root.title("ASI SPIM Acquisition Control")

        # GUI Variables
        self.num_slices_var = tk.IntVar(value=self.settings.num_slices)
        self.step_size_var = tk.DoubleVar(value=self.settings.step_size_um)
        self.num_time_points_var = tk.IntVar(value=1)
        self.time_interval_s_var = tk.DoubleVar(value=10.0)
        self.minimal_interval_var = tk.BooleanVar(value=False)
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

    def create_widgets(self):
        """Create and arrange all GUI elements."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        controls_frame = ttk.Labelframe(main_frame, text="Acquisition Settings")
        controls_frame.grid(row=0, column=0, sticky="ew", pady=5)
        controls_frame.grid_columnconfigure(1, weight=1)
        controls_frame.grid_columnconfigure(3, weight=1)

        # Time Series
        ttk.Label(controls_frame, text="Time Points").grid(
            row=0, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(controls_frame, textvariable=self.num_time_points_var).grid(
            row=0, column=1, sticky="ew", padx=5
        )
        ttk.Label(controls_frame, text="Interval (s)").grid(
            row=1, column=0, sticky="w", padx=5, pady=2
        )
        ttk.Entry(controls_frame, textvariable=self.time_interval_s_var).grid(
            row=1, column=1, sticky="ew", padx=5
        )
        ttk.Checkbutton(
            controls_frame, text="Minimal Interval", variable=self.minimal_interval_var
        ).grid(row=1, column=2, sticky="w", padx=5)

        ttk.Separator(controls_frame, orient="vertical").grid(
            row=0, column=2, rowspan=2, sticky="ns", padx=10
        )

        # Volume
        ttk.Label(controls_frame, text="Slices/Volume").grid(
            row=0, column=3, sticky="w", padx=5, pady=2
        )
        ttk.Entry(controls_frame, textvariable=self.num_slices_var).grid(
            row=0, column=4, sticky="ew", padx=5
        )
        ttk.Label(controls_frame, text="Step Size (µm)").grid(
            row=1, column=3, sticky="w", padx=5, pady=2
        )
        ttk.Entry(controls_frame, textvariable=self.step_size_var).grid(
            row=1, column=4, sticky="ew", padx=5
        )

        display_frame = ttk.Frame(main_frame)
        display_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        display_frame.grid_columnconfigure(0, weight=1)
        display_frame.grid_rowconfigure(0, weight=1)
        self.image_panel = ttk.Label(
            display_frame, text="Camera Image", background="black", anchor="center"
        )
        self.image_panel.grid(row=0, column=0, sticky="nsew")

        bottom_bar = ttk.Frame(main_frame)
        bottom_bar.grid(row=2, column=0, sticky="ew", pady=(5, 0))
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

    def start_time_series(self):
        """Set up and start the entire time-series acquisition."""
        if self.acquisition_in_progress:
            print("Warning: Acquisition already in progress.")
            return

        self.acquisition_in_progress = True
        self.run_button.configure(state="disabled")
        self.status_var.set("Initializing...")

        self.settings.num_slices = self.num_slices_var.get()
        self.settings.step_size_um = self.step_size_var.get()
        self.time_points_total = self.num_time_points_var.get()
        self.current_time_point = 0

        print("\n--- Starting Time Series ---")
        self._start_next_volume()

    def _start_next_volume(self):
        """Configure hardware and start the acquisition of a single volume."""
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

            print("Configuring devices for slice scan...")
            configure_devices_for_slice_scan(
                self.settings, galvo_amp, galvo_center, self.images_expected_per_volume
            )
            mmc.setExposure(self.hw_interface.camera1, self.settings.camera_exposure_ms)
            mmc.initializeCircularBuffer()
            mmc.startSequenceAcquisition(
                self.hw_interface.camera1, self.images_expected_per_volume, 0, True
            )

            self.volume_start_time = time.monotonic()
            print("Triggering acquisition...")
            trigger_slice_scan_acquisition()
            self.images_popped_this_volume = 0
            self.root.after(20, self._poll_for_images)

        except Exception as e:
            print(f"Error starting volume: {e}")
            traceback.print_exc()
            self._finish_time_series()

    def _poll_for_images(self):
        """Periodically check for and display new images from the camera."""
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
        """Called after one volume is complete; resets hardware and loops or ends."""
        volume_duration = time.monotonic() - self.volume_start_time
        print(
            f"Volume {self.current_time_point} acquired in {volume_duration:.2f} seconds."
        )

        _reset_for_next_volume()

        if self.current_time_point >= self.time_points_total:
            self._finish_time_series()
        else:
            interval_s = self.time_interval_s_var.get()
            delay_s = interval_s - volume_duration
            if self.minimal_interval_var.get() or delay_s < 0:
                delay_s = 0

            self.status_var.set(f"Waiting {delay_s:.1f}s for next time point...")
            print(f"Waiting {delay_s:.2f} seconds before next volume.")
            self.root.after(int(delay_s * 1000), self._start_next_volume)

    def _finish_time_series(self):
        """Clean up hardware and reset the GUI after the entire series."""
        print("\n--- Time Series Complete ---")
        final_cleanup(self.settings)
        self.hw_interface.find_and_set_trigger_mode(
            self.hw_interface.camera1, ["Internal", "Internal Trigger"]
        )
        self.acquisition_in_progress = False
        self.run_button.configure(state="normal")
        self.status_var.set("Ready")

    def _process_tagged_image(self, tagged_img) -> np.ndarray:
        """Convert a tagged image from MMCore to a numpy array."""
        height = int(tagged_img.tags.get("Height", 0))
        width = int(tagged_img.tags.get("Width", 0))
        return np.reshape(np.array(tagged_img.pix), (height, width))

    def display_image(self, img_array: np.ndarray):
        """Normalize and display the captured image in the GUI."""
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
        root.minsize(550, 600)
        app = AcquisitionGUI(root, hw_main_interface)
        root.mainloop()
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        if "mmc" in locals() and mmc.getLoadedDevices():
            mmc.reset()
        print("Script execution finished.")
