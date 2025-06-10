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
    print("Programming PLogic for One-Shot laser pulse with delays...")
    plogic_addr = HW.plogic_label[-2:]

    # Configure laser pulse duration
    _execute_tiger_serial_command(f"{plogic_addr}CCA X={HW.plogic_laser_preset_num}")
    _execute_tiger_serial_command(f"M E={HW.plogic_laser_on_cell}")
    _execute_tiger_serial_command("CCA Y=14")  # Set mode to one-shot
    pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_camera_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )

    # Configure delay before laser
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_laser_cell}")
    _execute_tiger_serial_command("CCA Y=13")  # Set mode to delay
    delay_cycles = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )

    # Configure delay before camera
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_camera_cell}")
    _execute_tiger_serial_command("CCA Y=13")  # Set mode to delay
    delay_cycles = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    print(
        f"PLogic configured. Laser pulse: {settings.laser_trig_duration_ms} ms, "
        f"Delay (Laser): {settings.delay_before_laser_ms} ms, "
        f"Delay (Camera): {settings.delay_before_camera_ms} ms."
    )


def reset_plogic_outputs():
    """Reset PLogic cells to a default state."""
    _execute_tiger_serial_command(f"M E={HW.plogic_laser_on_cell}")
    _execute_tiger_serial_command("CCA Z=0")
    _execute_tiger_serial_command("CCB X=0 Y=0")


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
    """Configure Galvo, Piezo, and PLogic for a slice scan."""
    print("Preparing controller for SLICE_SCAN_ONLY on Side A...")
    piezo_fixed_pos_um = round(settings.piezo_center_um, 3)

    set_property(HW.galvo_a_label, "BeamEnabled", "Yes")
    configure_plogic_for_one_shot_laser(settings)

    # Configure Galvo properties
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

    # Configure Piezo properties
    set_property(HW.piezo_a_label, "SingleAxisAmplitude(um)", 0.0)
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", piezo_fixed_pos_um)
    set_property(HW.piezo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.piezo_a_label, "SPIMState", "Armed")


def trigger_slice_scan_acquisition():
    """Trigger the armed SPIM state."""
    print("Triggering acquisition...")
    set_property(HW.galvo_a_label, "SPIMState", "Running")
    print("--- Acquisition Triggered ---")


def cleanup_slice_scan_devices(settings: AcquisitionSettings):
    """Return all devices to a safe, idle state."""
    print("Cleaning up controller...")
    set_property(HW.galvo_a_label, "BeamEnabled", "No")
    set_property(HW.galvo_a_label, "SPIMState", "Idle")
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)
    set_property(HW.piezo_a_label, "SPIMState", "Idle")
    reset_plogic_outputs()
    print("--- Cleanup Complete ---")


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
        """Return the primary camera device label."""
        return HW.camera_a_label

    def find_and_set_trigger_mode(
        self, camera_label: str, desired_modes: List[str]
    ) -> bool:
        """Find and set the first available trigger mode from a preferred list."""
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
                    print(
                        f"Successfully set {camera_label} '{trigger_prop}' to '{mode}'."
                    )
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
        self.laser_duration_var = tk.DoubleVar(
            value=self.settings.laser_trig_duration_ms
        )
        self.delay_before_camera_var = tk.DoubleVar(
            value=self.settings.delay_before_camera_ms
        )
        self.camera_exposure_var = tk.StringVar(
            value=f"{self.settings.camera_exposure_ms:.2f}"
        )
        self.delay_before_laser_var = tk.StringVar(
            value=f"{self.settings.delay_before_laser_ms:.2f}"
        )
        self._last_img = None  # To prevent garbage collection

        # Acquisition state
        self.images_expected = 0
        self.images_popped = 0
        self.acquisition_in_progress = False

        self.create_widgets()
        self.bind_traces()
        self.update_derived_values()

    def create_widgets(self):
        """Create and arrange all GUI elements."""
        frame = ttk.Frame(self.root, padding="10")
        frame.pack(fill="both", expand=True)

        # Grid configuration for resizing
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_rowconfigure(8, weight=1)  # Allow image panel to expand

        # Input fields
        ttk.Label(frame, text="Number of Slices").grid(
            row=0, column=0, sticky="w", pady=2
        )
        ttk.Entry(frame, textvariable=self.num_slices_var).grid(
            row=0, column=1, sticky="ew"
        )
        ttk.Label(frame, text="Step Size (µm)").grid(
            row=1, column=0, sticky="w", pady=2
        )
        ttk.Entry(frame, textvariable=self.step_size_var).grid(
            row=1, column=1, sticky="ew"
        )
        ttk.Label(frame, text="Laser Duration (ms)").grid(
            row=2, column=0, sticky="w", pady=2
        )
        ttk.Entry(frame, textvariable=self.laser_duration_var).grid(
            row=2, column=1, sticky="ew"
        )
        ttk.Label(frame, text="Delay Before Camera (ms)").grid(
            row=3, column=0, sticky="w", pady=2
        )
        ttk.Entry(frame, textvariable=self.delay_before_camera_var).grid(
            row=3, column=1, sticky="ew"
        )

        # Derived value display
        ttk.Separator(frame, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=5
        )
        ttk.Label(frame, text="Camera Exposure (ms)").grid(row=5, column=0, sticky="w")
        ttk.Label(frame, textvariable=self.camera_exposure_var, foreground="blue").grid(
            row=5, column=1, sticky="w"
        )
        ttk.Label(frame, text="Delay Before Laser (ms)").grid(
            row=6, column=0, sticky="w"
        )
        ttk.Label(
            frame, textvariable=self.delay_before_laser_var, foreground="blue"
        ).grid(row=6, column=1, sticky="w")
        ttk.Separator(frame, orient="horizontal").grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=5
        )

        # Image display panel
        self.image_panel = ttk.Label(
            frame, text="Camera Image", background="black", anchor="center"
        )
        self.image_panel.grid(row=8, column=0, columnspan=2, pady=10, sticky="nsew")

        # Control buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=9, column=0, columnspan=2, pady=5)
        self.run_button = ttk.Button(
            button_frame, text="Run Acquisition", command=self.run_acquisition
        )
        self.run_button.pack(side="left", padx=5)
        ttk.Button(button_frame, text="Exit", command=self.root.quit).pack(
            side="left", padx=5
        )

    def bind_traces(self):
        """Link GUI variable changes to the update function."""
        self.laser_duration_var.trace_add("write", self.on_input_change)
        self.delay_before_camera_var.trace_add("write", self.on_input_change)

    def on_input_change(self, *args):
        """Handle changes in input fields and update derived values."""
        try:
            self.settings.laser_trig_duration_ms = self.laser_duration_var.get()
            self.settings.delay_before_camera_ms = self.delay_before_camera_var.get()
        except (tk.TclError, ValueError):
            return  # Handle cases where entry is empty or has invalid text
        self.update_derived_values()

    def update_derived_values(self):
        """Recalculate and display derived settings."""
        self.camera_exposure_var.set(f"{self.settings.camera_exposure_ms:.2f}")
        self.delay_before_laser_var.set(f"{self.settings.delay_before_laser_ms:.2f}")

    def run_acquisition(self):
        """Set up and start the acquisition, then begin polling for images."""
        if self.acquisition_in_progress:
            print("Warning: Acquisition already in progress.")
            return

        self.acquisition_in_progress = True
        self.run_button.configure(state="disabled")

        # Update settings from GUI
        self.settings.num_slices = self.num_slices_var.get()
        self.settings.step_size_um = self.step_size_var.get()
        self.on_input_change()

        print("\nStarting acquisition with settings:")
        for key, val in self.settings.__dict__.items():
            print(f"  {key} = {val}")

        try:
            # Setup hardware for acquisition
            (
                galvo_amp,
                galvo_center,
                self.images_expected,
            ) = calculate_galvo_parameters(self.settings)

            mmc.setCameraDevice(self.hw_interface.camera1)
            if not self.hw_interface.find_and_set_trigger_mode(
                self.hw_interface.camera1, ["Edge Trigger", "External"]
            ):
                raise RuntimeError("Failed to set external trigger mode.")

            configure_devices_for_slice_scan(
                self.settings, galvo_amp, galvo_center, self.images_expected
            )
            mmc.setExposure(self.hw_interface.camera1, self.settings.camera_exposure_ms)
            mmc.initializeCircularBuffer()
            mmc.startSequenceAcquisition(
                self.hw_interface.camera1, self.images_expected, 0, True
            )

            # Trigger the hardware sequence
            trigger_slice_scan_acquisition()

            # Start polling for images
            self.images_popped = 0
            self.root.after(20, self._poll_for_images)

        except Exception as e:
            print(f"Error starting acquisition: {e}")
            traceback.print_exc()
            self._finish_acquisition()

    def _poll_for_images(self):
        """Periodically check for and display new images from the camera."""
        if not self.acquisition_in_progress:
            return

        # Pop and display an image if one is available
        if mmc.getRemainingImageCount() > 0:
            try:
                tagged_img = mmc.popNextTaggedImage()
                self.images_popped += 1
                print(f"  Popped image {self.images_popped}/{self.images_expected}")

                height = int(tagged_img.tags.get("Height", 0))
                width = int(tagged_img.tags.get("Width", 0))
                img_array = np.reshape(np.array(tagged_img.pix), (height, width))
                self.display_image(img_array)
            except Exception as e:
                print(f"Error popping image: {e}")
                self._finish_acquisition()
                return

        # Check if the acquisition is complete
        if self.images_popped >= self.images_expected:
            print("Acquisition complete.")
            self._finish_acquisition()
            return

        # Check if sequence was aborted externally
        if (
            not mmc.isSequenceRunning(self.hw_interface.camera1)
            and mmc.getRemainingImageCount() == 0
        ):
            print("Warning: Sequence stopped unexpectedly.")
            self._finish_acquisition()
            return

        # Schedule the next poll
        self.root.after(20, self._poll_for_images)

    def _finish_acquisition(self):
        """Clean up hardware and reset the GUI to its idle state."""
        print("Finishing acquisition...")
        cleanup_slice_scan_devices(self.settings)
        # Return camera to internal trigger mode for general use
        self.hw_interface.find_and_set_trigger_mode(
            self.hw_interface.camera1, ["Internal", "Internal Trigger"]
        )
        self.acquisition_in_progress = False
        self.run_button.configure(state="normal")
        print("--- GUI Ready ---")

    def display_image(self, img_array: np.ndarray):
        """Normalize and display the captured image in the GUI."""
        try:
            # Normalize to 8-bit for display
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
            self._last_img = tk_img  # Keep reference
        except Exception as e:
            print(f"Error processing image for display: {e}")


if __name__ == "__main__":
    try:
        hw_main_interface = HardwareInterface(config_file_path=HW.cfg_path)
        root = tk.Tk()
        root.minsize(400, 600)
        app = AcquisitionGUI(root, hw_main_interface)
        root.mainloop()
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        if "mmc" in locals() and mmc.getLoadedDevices():
            mmc.reset()
        print("Script execution finished.")
