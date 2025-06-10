from pymmcore_plus import CMMCorePlus
from typing import Optional, List
import traceback
import time
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import numpy as np


# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- Acquisition Settings ---
NUM_SLICES_SETTING = 3
STEP_SIZE_UM = 1.0
PIEZO_CENTER_UM = -31.0
LASER_TRIG_DURATION_MS = 10  # Effective exposure time for the sample
DELAY_BEFORE_CAMERA_MS = 18  # Used to derive DELAY_BEFORE_LASER_MS
CAMERA_EXPOSURE_MS = LASER_TRIG_DURATION_MS + 1.95
DELAY_BEFORE_LASER_MS = DELAY_BEFORE_CAMERA_MS + 1.25

# --- Global Constants and Configuration ---
CFG_PATH = "hardware_profiles/20250523-OPM.cfg"

# Device labels
GALVO_A_LABEL = "Scanner:AB:33"
PIEZO_A_LABEL = "PiezoStage:P:34"
CAMERA_A_LABEL = "Camera-1"
PLOGIC_LABEL = "PLogic:E:36"
TIGER_COMM_HUB_LABEL = "TigerCommHub"

# --- PLogic Addresses and Presets ---
PLOGIC_CAMERA_TRIGGER_TTL_ADDR = 44
PLOGIC_LASER_TRIGGER_TTL_ADDR = 45
PLOGIC_4KHZ_CLOCK_ADDR = 192
PLOGIC_LASER_ON_CELL = 10
PLOGIC_LASER_PRESET_NUM = 5
PULSES_PER_MS = 4.0
PLOGIC_GALVO_TRIGGER_TTL_ADDR = 43

# Calibration parameters
SLICE_CALIBRATION_SLOPE_UM_PER_DEG = 100.0
SLICE_CALIBRATION_OFFSET_UM = 0.0

# Timing Parameters CONSTANTS
DELAY_BEFORE_SCAN_MS = 0
LINE_SCANS_PER_SLICE = 1
LINE_SCAN_DURATION_MS = 1
CAMERA_TRIG_DURATION_MS = 1
NUM_SIDES = 1
FIRST_SIDE_IS_A = True
SCAN_OPPOSITE_DIRECTIONS = False
SHEET_WIDTH_DEG = 0.5
SHEET_OFFSET_DEG = 0.0
DELAY_BEFORE_SIDE_MS = 0.0
SCAN_PERIOD_MS = LINE_SCANS_PER_SLICE * LINE_SCAN_DURATION_MS + DELAY_BEFORE_SCAN_MS
CAMERA_MODE_IS_OVERLAP = False

# PLogic Cell Addresses for Delays
PLOGIC_DELAY_BEFORE_LASER_CELL = 11
PLOGIC_DELAY_BEFORE_CAMERA_CELL = 12


# --- Low-Level Helper Functions ---
def _execute_tiger_serial_command(command_string: str):
    original_setting = mmc.getProperty(
        TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "No")
    mmc.setProperty(TIGER_COMM_HUB_LABEL, "SerialCommand", command_string)
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "Yes")
    time.sleep(0.02)


def set_property(device_label, property_name, value):
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        mmc.setProperty(device_label, property_name, value)
    else:
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found."
        )


def configure_plogic_for_one_shot_laser():
    print("Programming PLogic for One-Shot laser pulse with delays...")
    _execute_tiger_serial_command(f"{PLOGIC_LABEL[-2:]}CCA X={PLOGIC_LASER_PRESET_NUM}")
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    _execute_tiger_serial_command("CCA Y=14")
    pulse_duration_cycles = int(LASER_TRIG_DURATION_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_CAMERA_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )

    _execute_tiger_serial_command(f"M E={PLOGIC_DELAY_BEFORE_LASER_CELL}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_before_laser_cycles = int(DELAY_BEFORE_LASER_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(f"CCA Z={delay_before_laser_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )

    _execute_tiger_serial_command(f"M E={PLOGIC_DELAY_BEFORE_CAMERA_CELL}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_before_camera_cycles = int(DELAY_BEFORE_CAMERA_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(f"CCA Z={delay_before_camera_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )

    print(
        f"PLogic configured. Laser pulse duration set to {LASER_TRIG_DURATION_MS} ms,"
        f" delay before laser: {DELAY_BEFORE_LASER_MS} ms, delay before camera: {DELAY_BEFORE_CAMERA_MS} ms."
    )


def reset_plogic_outputs():
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    _execute_tiger_serial_command("CCA Z=0")
    _execute_tiger_serial_command("CCB X=0 Y=0")


def calculate_galvo_parameters():
    if abs(SLICE_CALIBRATION_SLOPE_UM_PER_DEG) < 1e-9:
        raise ValueError("Slice calibration slope cannot be zero.")
    num_slices_for_controller = NUM_SLICES_SETTING
    piezo_amplitude_initial_um = (num_slices_for_controller - 1) * STEP_SIZE_UM
    if CAMERA_MODE_IS_OVERLAP:
        if num_slices_for_controller > 1:
            piezo_amplitude_initial_um *= float(num_slices_for_controller) / (
                num_slices_for_controller - 1.0
            )
        num_slices_for_controller += 1
    galvo_slice_amplitude_deg = (
        piezo_amplitude_initial_um / SLICE_CALIBRATION_SLOPE_UM_PER_DEG
    )
    galvo_slice_center_deg = (
        PIEZO_CENTER_UM - SLICE_CALIBRATION_OFFSET_UM
    ) / SLICE_CALIBRATION_SLOPE_UM_PER_DEG
    return (
        round(galvo_slice_amplitude_deg, 4),
        round(galvo_slice_center_deg, 4),
        num_slices_for_controller,
    )


def configure_devices_for_slice_scan(
    galvo_slice_amplitude_deg,
    galvo_slice_center_deg,
    piezo_fixed_position_um,
    num_slices_ctrl,
):
    print("Preparing controller for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "Yes")
    configure_plogic_for_one_shot_laser()
    set_property(GALVO_A_LABEL, "SPIMNumSlicesPerPiezo", LINE_SCANS_PER_SLICE)
    set_property(GALVO_A_LABEL, "SPIMDelayBeforeRepeat(ms)", DELAY_BEFORE_SCAN_MS)
    set_property(GALVO_A_LABEL, "SPIMNumRepeats", 1)
    set_property(GALVO_A_LABEL, "SPIMDelayBeforeSide(ms)", DELAY_BEFORE_SIDE_MS)
    set_property(
        GALVO_A_LABEL,
        "SPIMAlternateDirectionsEnable",
        "Yes" if SCAN_OPPOSITE_DIRECTIONS else "No",
    )
    set_property(GALVO_A_LABEL, "SPIMScanDuration(ms)", LINE_SCAN_DURATION_MS)
    set_property(GALVO_A_LABEL, "SingleAxisYAmplitude(deg)", galvo_slice_amplitude_deg)
    set_property(GALVO_A_LABEL, "SingleAxisYOffset(deg)", galvo_slice_center_deg)
    set_property(GALVO_A_LABEL, "SPIMNumSlices", num_slices_ctrl)
    set_property(GALVO_A_LABEL, "SPIMNumSides", NUM_SIDES)
    set_property(GALVO_A_LABEL, "SPIMFirstSide", "A" if FIRST_SIDE_IS_A else "B")
    set_property(GALVO_A_LABEL, "SPIMPiezoHomeDisable", "No")
    set_property(GALVO_A_LABEL, "SPIMInterleaveSidesEnable", "No")
    set_property(GALVO_A_LABEL, "SingleAxisXAmplitude(deg)", SHEET_WIDTH_DEG)
    set_property(GALVO_A_LABEL, "SingleAxisXOffset(deg)", SHEET_OFFSET_DEG)

    set_property(PIEZO_A_LABEL, "SingleAxisAmplitude(um)", 0.0)
    set_property(PIEZO_A_LABEL, "SingleAxisOffset(um)", piezo_fixed_position_um)
    set_property(PIEZO_A_LABEL, "SPIMNumSlices", num_slices_ctrl)
    set_property(PIEZO_A_LABEL, "SPIMState", "Armed")


def trigger_slice_scan_acquisition():
    print("Triggering acquisition for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "SPIMState", "Running")
    print("--- Acquisition Triggered ---")


def cleanup_slice_scan_devices():
    print("Cleaning up controller for Side A...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "No")
    set_property(GALVO_A_LABEL, "SPIMState", "Idle")
    set_property(PIEZO_A_LABEL, "SingleAxisOffset(um)", PIEZO_CENTER_UM)
    set_property(PIEZO_A_LABEL, "SPIMState", "Idle")
    reset_plogic_outputs()
    print("--- Cleanup Complete ---")


def wait_for_camera_acquisition(
    camera_label,
    num_images_expected,
    first_image_timeout_s=10.0,
    inter_image_timeout_s=5.0,
):
    print(f"Waiting for {num_images_expected} images from {camera_label}...")
    images_popped = 0
    start_time = time.monotonic()
    last_image_time = start_time
    while images_popped < num_images_expected:
        current_time = time.monotonic()
        if (
            not mmc.isSequenceRunning(camera_label)
            and mmc.getRemainingImageCount() == 0
        ):
            print(
                f"Warning: Camera sequence stopped early. Received {images_popped}/{num_images_expected}."
            )
            break
        if (current_time - start_time) > first_image_timeout_s and images_popped == 0:
            print("Timeout waiting for first image.")
            break
        if (current_time - last_image_time) > inter_image_timeout_s:
            print("Timeout between images.")
            break
        if mmc.getRemainingImageCount() > 0:
            try:
                tagged_img = mmc.popNextTaggedImage()
                height = int(tagged_img.tags.get("Height", 0))
                width = int(tagged_img.tags.get("Width", 0))
                img_array = np.reshape(np.array(tagged_img.pix), (height, width))
                images_popped += 1
                last_image_time = current_time
                return img_array  # Return last image array
            except Exception as e:
                print(f"Error popping image: {e}")
                break
        else:
            time.sleep(0.01)
    return None


# --- HardwareInterface Class ---
class HardwareInterface:
    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        print("Initializing HardwareInterface...")
        current_loaded_config = mmc.systemConfigurationFile() or ""
        target_config = self.config_path
        if not target_config:
            if "TigerCommHub" in mmc.getLoadedDevices():
                print(f"Using existing MMCore config: {current_loaded_config}")
                return
            else:
                raise FileNotFoundError(
                    "HardwareInterface requires a config_path, and no valid ASI config is loaded."
                )
        if not os.path.isabs(target_config):
            target_config = os.path.abspath(target_config)
        if os.path.normcase(current_loaded_config) == os.path.normcase(target_config):
            print(f"Target configuration '{target_config}' is already loaded.")
            return
        print(f"Attempting to load configuration: '{target_config}'")
        try:
            mmc.loadSystemConfiguration(target_config)
            if "TigerCommHub" not in mmc.getLoadedDevices():
                raise RuntimeError(
                    "Loaded configuration does not appear to contain an ASI TigerCommHub."
                )
            print(f"Successfully loaded configuration: {mmc.systemConfigurationFile()}")
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{target_config}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        return CAMERA_A_LABEL

    def find_and_set_trigger_mode(
        self, camera_label: str, desired_modes: List[str]
    ) -> bool:
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Camera device '{camera_label}' not found.")
            return False
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            print(
                f"Error: Camera '{camera_label}' does not have property '{trigger_prop}'."
            )
            return False
        try:
            allowed_modes = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
            for mode in desired_modes:
                if mode in allowed_modes:
                    set_property(camera_label, trigger_prop, mode)
                    print(
                        f"Successfully set {camera_label} '{trigger_prop}' to '{mode}'."
                    )
                    return True
            print(
                f"Error: None of the desired trigger modes {desired_modes} are available."
            )
            return False
        except Exception as e:
            print(f"Error setting trigger mode for {camera_label}: {e}")
            return False


# --- Main Execution Function ---
def run_acquisition_sequence(hw_interface: HardwareInterface):
    galvo_amp_deg, galvo_center_deg, num_slices_for_ctrl = calculate_galvo_parameters()
    piezo_fixed_pos_um = round(PIEZO_CENTER_UM, 3)
    try:
        mmc.setCameraDevice(hw_interface.camera1)
        external_trigger_modes = ["Edge Trigger"]
        if not hw_interface.find_and_set_trigger_mode(
            hw_interface.camera1, external_trigger_modes
        ):
            print(
                f"Failed to set {hw_interface.camera1} to a valid external trigger mode. Aborting."
            )
            return

        configure_devices_for_slice_scan(
            galvo_amp_deg, galvo_center_deg, piezo_fixed_pos_um, num_slices_for_ctrl
        )
        mmc.setExposure(hw_interface.camera1, CAMERA_EXPOSURE_MS)
        mmc.initializeCircularBuffer()
        mmc.startSequenceAcquisition(hw_interface.camera1, num_slices_for_ctrl, 0, True)
        trigger_slice_scan_acquisition()
        img_array = wait_for_camera_acquisition(
            hw_interface.camera1, num_slices_for_ctrl
        )
        return img_array

    except Exception as e:
        print(f"An error occurred during acquisition sequence: {e}")
        traceback.print_exc()
    finally:
        cleanup_slice_scan_devices()
        internal_trigger_modes = ["Internal", "Internal Trigger"]
        hw_interface.find_and_set_trigger_mode(
            hw_interface.camera1, internal_trigger_modes
        )
    return None


# --- Tkinter GUI with Live Image Display ---
class AcquisitionGUI:
    def __init__(self, root, hw_interface):
        self.root = root
        self.hw_interface = hw_interface
        self.root.title("ASI SPIM Acquisition Control")

        # Variables
        self.num_slices_var = tk.IntVar(value=NUM_SLICES_SETTING)
        self.step_size_var = tk.DoubleVar(value=STEP_SIZE_UM)
        self.laser_duration_var = tk.DoubleVar(value=LASER_TRIG_DURATION_MS)
        self.delay_before_camera_var = tk.DoubleVar(value=DELAY_BEFORE_CAMERA_MS)

        self.camera_exposure_var = tk.StringVar(value=f"{CAMERA_EXPOSURE_MS:.2f}")
        self.delay_before_laser_var = tk.StringVar(value=f"{DELAY_BEFORE_LASER_MS:.2f}")

        self.create_widgets()
        self.bind_traces()

    def create_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        ttk.Label(frame, text="NUM_SLICES_SETTING").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.num_slices_var).grid(row=0, column=1)

        ttk.Label(frame, text="STEP_SIZE_UM").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.step_size_var).grid(row=1, column=1)

        ttk.Label(frame, text="LASER_TRIG_DURATION_MS").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(frame, textvariable=self.laser_duration_var).grid(row=2, column=1)

        ttk.Label(frame, text="DELAY_BEFORE_CAMERA_MS").grid(
            row=3, column=0, sticky="w"
        )
        ttk.Entry(frame, textvariable=self.delay_before_camera_var).grid(
            row=3, column=1
        )

        ttk.Label(frame, text="CAMERA_EXPOSURE_MS (auto)").grid(
            row=4, column=0, sticky="w"
        )
        ttk.Label(frame, textvariable=self.camera_exposure_var, foreground="blue").grid(
            row=4, column=1
        )

        ttk.Label(frame, text="DELAY_BEFORE_LASER_MS (auto)").grid(
            row=5, column=0, sticky="w"
        )
        ttk.Label(
            frame, textvariable=self.delay_before_laser_var, foreground="blue"
        ).grid(row=5, column=1)

        ttk.Button(frame, text="Run Acquisition", command=self.run_acquisition).grid(
            row=6, column=0, pady=10
        )
        ttk.Button(frame, text="Exit", command=self.root.quit).grid(
            row=6, column=1, pady=10
        )

        self.image_panel = tk.Label(frame, text="Camera Image", bg="black")
        self.image_panel.grid(row=7, column=0, columnspan=2, pady=10, sticky="nsew")

    def bind_traces(self):
        self.laser_duration_var.trace_add("write", self.on_input_change)
        self.delay_before_camera_var.trace_add("write", self.on_input_change)

    def on_input_change(self, *args):
        global \
            LASER_TRIG_DURATION_MS, \
            DELAY_BEFORE_CAMERA_MS, \
            DELAY_BEFORE_LASER_MS, \
            CAMERA_EXPOSURE_MS
        try:
            LASER_TRIG_DURATION_MS = self.laser_duration_var.get()
            DELAY_BEFORE_CAMERA_MS = self.delay_before_camera_var.get()
        except tk.TclError:
            return
        self.update_derived_values()

    def update_derived_values(self):
        global DELAY_BEFORE_LASER_MS, CAMERA_EXPOSURE_MS
        DELAY_BEFORE_LASER_MS = DELAY_BEFORE_CAMERA_MS + 1.25
        CAMERA_EXPOSURE_MS = LASER_TRIG_DURATION_MS + 1.95
        self.camera_exposure_var.set(f"{CAMERA_EXPOSURE_MS:.2f}")
        self.delay_before_laser_var.set(f"{DELAY_BEFORE_LASER_MS:.2f}")

    def run_acquisition(self):
        global NUM_SLICES_SETTING, STEP_SIZE_UM
        NUM_SLICES_SETTING = self.num_slices_var.get()
        STEP_SIZE_UM = self.step_size_var.get()
        self.update_derived_values()

        print("\nRunning acquisition with settings:")
        print(f"  NUM_SLICES_SETTING = {NUM_SLICES_SETTING}")
        print(f"  STEP_SIZE_UM = {STEP_SIZE_UM}")
        print(f"  LASER_TRIG_DURATION_MS = {LASER_TRIG_DURATION_MS}")
        print(f"  DELAY_BEFORE_CAMERA_MS = {DELAY_BEFORE_CAMERA_MS}")
        print(f"  DELAY_BEFORE_LASER_MS = {DELAY_BEFORE_LASER_MS}")
        print(f"  CAMERA_EXPOSURE_MS = {CAMERA_EXPOSURE_MS}")

        img_array = run_acquisition_sequence(self.hw_interface)
        if img_array is not None:
            try:
                # Normalize image data to 8-bit grayscale
                img_min, img_max = img_array.min(), img_array.max()
                if img_min == img_max:
                    img_normalized = np.zeros_like(img_array, dtype=np.uint8)
                else:
                    img_normalized = ((img_array - img_min) / (img_max - img_min) * 255).astype(np.uint8)

                # Convert to PIL Image
                pil_img = Image.fromarray(img_normalized)

                # Resize for display (e.g., 600x600 pixels)
                display_size = (600, 600)  # W x H
                pil_img = pil_img.resize(display_size, Image.Resampling.LANCZOS)

                # Convert to Tkinter-compatible format
                self.tk_img = ImageTk.PhotoImage(pil_img)

                # Update label with new image
                self.image_panel.configure(image=self.tk_img)
                # Keep a reference to avoid garbage collection
                self._last_img = self.tk_img

            except Exception as img_error:
                print(f"Error processing image for display: {img_error}")

if __name__ == "__main__":
    try:
        hw_main_interface = HardwareInterface(config_file_path=CFG_PATH)

        root = tk.Tk()
        app = AcquisitionGUI(root, hw_main_interface)
        root.mainloop()

    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        print("Script execution finished.")
