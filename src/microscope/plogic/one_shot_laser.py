from pymmcore_plus import CMMCorePlus
from typing import Optional, List
import traceback
import time
import os
import tkinter as tk
from tkinter import scrolledtext
import threading

# --- Acquisition Settings ---
NUM_SLICES_SETTING = 3
STEP_SIZE_UM = 1.0
PIEZO_CENTER_UM = -31.0
LASER_TRIG_DURATION_MS = 10  # Effective exposure time for the sample

# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- Global Constants and Configuration ---
CFG_PATH = "hardware_profiles/20250523-OPM.cfg"

# Device labels
GALVO_A_LABEL = "Scanner:AB:33"
PIEZO_A_LABEL = "PiezoStage:P:34"
CAMERA_A_LABEL = "Camera-1"
PLOGIC_LABEL = "PLogic:E:36"
TIGER_COMM_HUB_LABEL = "TigerCommHub"

# --- PLogic Addresses and Presets ---
# Input Address for the per-slice "Camera Trigger" signal (TTL-4)
PLOGIC_CAMERA_TRIGGER_TTL_ADDR = 44
# Input Address for the per-slice "Laser Trigger" signal (TTL-5)
PLOGIC_LASER_TRIGGER_TTL_ADDR = 45
# Input Address for the 4kHz internal evaluation clock
PLOGIC_4KHZ_CLOCK_ADDR = 192
# Internal Cell Address for the master "laser on" signal
PLOGIC_LASER_ON_CELL = 10
# The preset number that routes internal cells to BNC outputs
PLOGIC_LASER_PRESET_NUM = 5
# Pulses per millisecond for timing calculations
PULSES_PER_MS = 4.0
# Address for the galvo trigger signal (TTL-3)
PLOGIC_GALVO_TRIGGER_TTL_ADDR = 43

# Calibration parameters for slice scanning
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
DELAY_BEFORE_CAMERA_MS = 1.25  # 18
DELAY_BEFORE_LASER_MS = DELAY_BEFORE_CAMERA_MS + 1.25
CAMERA_EXPOSURE_MS = LASER_TRIG_DURATION_MS + 1.95

# Camera mode settings
CAMERA_MODE_IS_OVERLAP = False  # True for overlap mode, False for non-overlap
SCAN_PERIOD_MS = LINE_SCANS_PER_SLICE * LINE_SCAN_DURATION_MS + DELAY_BEFORE_SCAN_MS

# PLogic Cell Addresses for Delays
PLOGIC_DELAY_BEFORE_LASER_CELL = 11  # Cell for delay before laser
PLOGIC_DELAY_BEFORE_CAMERA_CELL = 12  # Cell for delay before camera


# --- Low-Level Helper Functions ---
def _execute_tiger_serial_command(command_string: str):
    """Sends a command via TigerCommHub."""
    original_setting = mmc.getProperty(
        TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "No")

    mmc.setProperty(TIGER_COMM_HUB_LABEL, "SerialCommand", command_string)

    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "Yes")

    time.sleep(0.01)


def set_property(device_label, property_name, value):
    """Sets a device property if the device exists and has the property."""
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        mmc.setProperty(device_label, property_name, value)
    else:
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found."
        )


def configure_plogic_for_one_shot_laser():
    """
    Configures the PLogic card to generate a laser pulse of a specific
    duration (one-shot) triggered by the camera's trigger signal,
    including delays before laser and camera.
    """
    print("Programming PLogic for One-Shot laser pulse with delays...")

    # Step 1: Apply Preset 5 to route internal cells to BNC outputs.
    print(f"Applying PLogic Preset {PLOGIC_LASER_PRESET_NUM} for BNC routing...")
    _execute_tiger_serial_command(f"{PLOGIC_LABEL[-2:]}CCA X={PLOGIC_LASER_PRESET_NUM}")

    # Step 2: Configure Cell 10 as a "one-shot (non-retriggerable)" timer for laser.
    print(f"Configuring Cell {PLOGIC_LASER_ON_CELL} as a one-shot timer...")
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    _execute_tiger_serial_command("CCA Y=14")  # Set cell type to one-shot
    pulse_duration_cycles = int(LASER_TRIG_DURATION_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")  # Set duration
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_CAMERA_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )  # Inputs: Trigger from camera, 4kHz clock

    # Step 3: Configure Cell 11 for delay before laser.
    print(
        f"Configuring Cell {PLOGIC_DELAY_BEFORE_LASER_CELL} for delay before laser..."
    )
    _execute_tiger_serial_command(f"M E={PLOGIC_DELAY_BEFORE_LASER_CELL}")
    _execute_tiger_serial_command("CCA Y=13")  # Set cell type to delay
    delay_before_laser_cycles = int(DELAY_BEFORE_LASER_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(
        f"CCA Z={delay_before_laser_cycles}"
    )  # Set delay duration
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )  # Inputs: Trigger from galvo, 4kHz clock

    # Step 4: Configure Cell 12 for delay before camera.
    print(
        f"Configuring Cell {PLOGIC_DELAY_BEFORE_CAMERA_CELL} for delay before camera..."
    )
    _execute_tiger_serial_command(f"M E={PLOGIC_DELAY_BEFORE_CAMERA_CELL}")
    _execute_tiger_serial_command("CCA Y=13")  # Set cell type to delay
    delay_before_camera_cycles = int(DELAY_BEFORE_CAMERA_MS * PULSES_PER_MS)
    _execute_tiger_serial_command(
        f"CCA Z={delay_before_camera_cycles}"
    )  # Set delay duration
    _execute_tiger_serial_command(
        f"CCB X={PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={PLOGIC_4KHZ_CLOCK_ADDR}"
    )  # Inputs: Trigger from galvo, 4kHz clock

    print(
        f"PLogic configured. "
        f"Laser pulse duration set to {LASER_TRIG_DURATION_MS} ms, "
        f"delay before laser set to {DELAY_BEFORE_LASER_MS} ms, "
        f"delay before camera set to {DELAY_BEFORE_CAMERA_MS} ms."
    )


def configure_devices_for_slice_scan(
    galvo_slice_amplitude_deg,
    galvo_slice_center_deg,
    piezo_fixed_position_um,
    num_slices_ctrl,
):
    """Configures Galvo, Piezo, and PLogic for the SPIM acquisition."""
    print("Preparing controller for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "Yes")
    configure_plogic_for_one_shot_laser()

    # Galvo Device Configuration
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

    # Piezo Device Configuration
    set_property(PIEZO_A_LABEL, "SingleAxisAmplitude(um)", 0.0)
    set_property(PIEZO_A_LABEL, "SingleAxisOffset(um)", piezo_fixed_position_um)
    set_property(PIEZO_A_LABEL, "SPIMNumSlices", num_slices_ctrl)
    set_property(PIEZO_A_LABEL, "SPIMState", "Armed")


def reset_plogic_outputs():
    """Resets the master laser cell to be off."""
    print("Resetting PLogic master laser cell to OFF...")
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    _execute_tiger_serial_command("CCA Z=0")  # Set duration to 0
    _execute_tiger_serial_command("CCB X=0 Y=0")  # Set inputs to ground
    print("PLogic outputs reset.")


# --- Calculations ---
def calculate_galvo_parameters():
    """Calculates galvo scan parameters from acquisition settings."""
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


def trigger_slice_scan_acquisition():
    """Triggers the SPIM acquisition on the Galvo device."""
    print("Triggering acquisition for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "SPIMState", "Running")
    print("--- Acquisition Triggered ---")


def cleanup_slice_scan_devices():
    """Resets devices to an idle state after acquisition."""
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
    """Waits for and drains images from the camera's circular buffer."""
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
            print(f"Timeout: First image not received within {first_image_timeout_s}s.")
            break

        if (current_time - last_image_time) > inter_image_timeout_s:
            print(
                f"Timeout: No new image for {inter_image_timeout_s}s. Received {images_popped}/{num_images_expected}."
            )
            break

        if mmc.getRemainingImageCount() > 0:
            try:
                _ = mmc.popNextTaggedImage()
                images_popped += 1
                last_image_time = current_time
            except Exception as e:
                print(f"Error popping image: {e}")
                break
        else:
            time.sleep(0.001)

    if mmc.isSequenceRunning(camera_label):
        mmc.stopSequenceAcquisition(camera_label)
        print("Stopped camera sequence.")

    while mmc.getRemainingImageCount() > 0:
        try:
            mmc.popNextTaggedImage()
        except Exception:
            break

    print(f"Finished waiting. Acquired {images_popped} images.")
    return images_popped


# --- HardwareInterface Class ---
class HardwareInterface:
    """A simplified class to manage hardware initialization via MMCorePlus."""

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
        """Finds and sets the first available trigger mode from a preferred list."""
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
                f"Error: None of the desired trigger modes {desired_modes} are available. Allowed modes: {list(allowed_modes)}"
            )
            return False
        except Exception as e:
            print(f"Error setting trigger mode for {camera_label}: {e}")
            return False


# --- Main Script Execution ---
def run_acquisition_sequence(hw_interface: HardwareInterface):
    """Orchestrates the SLICE_SCAN_ONLY acquisition."""
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

        wait_for_camera_acquisition(hw_interface.camera1, num_slices_for_ctrl)

    except Exception as e:
        print(f"An error occurred during acquisition sequence: {e}")
        traceback.print_exc()
    finally:
        cleanup_slice_scan_devices()
        internal_trigger_modes = ["Internal", "Internal Trigger"]
        hw_interface.find_and_set_trigger_mode(
            hw_interface.camera1, internal_trigger_modes
        )


class AcquisitionGUI:
    def __init__(self, root, hw_interface):
        self.root = root
        self.hw_interface = hw_interface
        self.root.title("ASI SPIM Acquisition Control")

        # Global variables to track user input
        self.num_slices_var = tk.IntVar(value=NUM_SLICES_SETTING)
        self.step_size_var = tk.DoubleVar(value=STEP_SIZE_UM)
        self.laser_duration_var = tk.DoubleVar(value=LASER_TRIG_DURATION_MS)
        self.delay_before_camera_var = tk.DoubleVar(value=DELAY_BEFORE_CAMERA_MS)

        # Layout
        self.create_widgets()
        self.redirect_output()

    def create_widgets(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10)

        tk.Label(frame, text="NUM_SLICES_SETTING").grid(row=0, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.num_slices_var).grid(row=0, column=1)

        tk.Label(frame, text="STEP_SIZE_UM").grid(row=1, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.step_size_var).grid(row=1, column=1)

        tk.Label(frame, text="LASER_TRIG_DURATION_MS").grid(row=2, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.laser_duration_var).grid(row=2, column=1)

        tk.Label(frame, text="DELAY_BEFORE_CAMERA_MS").grid(row=3, column=0, sticky="w")
        tk.Entry(frame, textvariable=self.delay_before_camera_var).grid(row=3, column=1)

        tk.Button(frame, text="Run Acquisition", command=self.run_acquisition).grid(
            row=4, column=0, pady=5
        )
        tk.Button(frame, text="Retrigger", command=self.run_acquisition).grid(
            row=4, column=1, pady=5
        )
        tk.Button(frame, text="Exit", command=self.root.quit).grid(
            row=4, column=2, pady=5
        )

        # Output console
        self.console = scrolledtext.ScrolledText(frame, height=15, width=60)
        self.console.grid(row=5, column=0, columnspan=3, pady=10)

    def redirect_output(self):
        import sys
        from io import StringIO

        class RedirectOutput(StringIO):
            def __init__(self, widget):
                super().__init__()
                self.widget = widget

            def write(self, string): # type: ignore
                self.widget.insert(tk.END, string)
                self.widget.see(tk.END)

        sys.stdout = RedirectOutput(self.console)
        sys.stderr = RedirectOutput(self.console)

    def run_acquisition(self):
        global \
            NUM_SLICES_SETTING, \
            STEP_SIZE_UM, \
            LASER_TRIG_DURATION_MS, \
            DELAY_BEFORE_CAMERA_MS, \
            CAMERA_EXPOSURE_MS, \
            DELAY_BEFORE_LASER_MS

        try:
            NUM_SLICES_SETTING = self.num_slices_var.get()
            STEP_SIZE_UM = self.step_size_var.get()
            LASER_TRIG_DURATION_MS = self.laser_duration_var.get()
            DELAY_BEFORE_CAMERA_MS = self.delay_before_camera_var.get()
            DELAY_BEFORE_LASER_MS = DELAY_BEFORE_CAMERA_MS + 1.25
            CAMERA_EXPOSURE_MS = LASER_TRIG_DURATION_MS + 1.95

            print("\nRunning acquisition with settings:")
            print(f"  NUM_SLICES_SETTING = {NUM_SLICES_SETTING}")
            print(f"  STEP_SIZE_UM = {STEP_SIZE_UM}")
            print(f"  LASER_TRIG_DURATION_MS = {LASER_TRIG_DURATION_MS}")
            print(f"  DELAY_BEFORE_CAMERA_MS = {DELAY_BEFORE_CAMERA_MS}")
            print(f"  DELAY_BEFORE_LASER_MS = {DELAY_BEFORE_LASER_MS}")
            print(f"  CAMERA_EXPOSURE_MS = {CAMERA_EXPOSURE_MS}")

            # Run in separate thread to avoid freezing GUI
            threading.Thread(
                target=run_acquisition_sequence, args=(self.hw_interface,), daemon=True
            ).start()

        except Exception as e:
            print(f"Error updating parameters: {e}")


def start_gui():
    try:
        hw_main_interface = HardwareInterface(config_file_path=CFG_PATH)
    except Exception as e:
        print(f"Hardware initialization failed: {e}")
        return

    root = tk.Tk()
    app = AcquisitionGUI(root, hw_main_interface)  # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    start_gui()
