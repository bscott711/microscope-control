import os
import time
import traceback
from typing import List, Optional

from pymmcore_plus import CMMCorePlus

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
# Input Address for the per-slice "Laser Trigger" signal (TTL-5)
PLOGIC_LASER_TRIGGER_TTL_ADDR = 45
# Internal Cell Address for the master "laser on" signal
PLOGIC_LASER_ON_CELL = 10
# The preset number that configures BNC outputs for laser control
PLOGIC_LASER_PRESET_NUM = 5

# --- Acquisition Settings ---
NUM_SLICES_SETTING = 10
STEP_SIZE_UM = 1.0
PIEZO_CENTER_UM = -31.0
SLICE_CALIBRATION_SLOPE_UM_PER_DEG = 100.0
SLICE_CALIBRATION_OFFSET_UM = 0.0
CAMERA_MODE_IS_OVERLAP = False
SCAN_PERIOD_MS = 10.0
CAMERA_EXPOSURE_MS = 10.0
NUM_SIDES = 1
FIRST_SIDE_IS_A = True
SCAN_OPPOSITE_DIRECTIONS = False
DELAY_BEFORE_SIDE_MS = 50.0
SHEET_WIDTH_DEG = 0.5
SHEET_OFFSET_DEG = 0.0


# --- Low-Level Helper Functions ---
def _execute_tiger_serial_command(command_string: str):
    """Sends a command via TigerCommHub."""
    original_setting = mmc.getProperty(
        TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "No")

    mmc.setProperty(TIGER_COMM_HUB_LABEL, "SerialCommand", command_string)

    # Restore original setting
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "Yes")

    time.sleep(0.01)  # Small delay for command to be processed


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


# --- PLogic Configuration Functions ---
def configure_plogic_for_laser_control_with_preset():
    """
    Configures the PLogic card using a preset for BNC routing, then
    links the master laser control cell to the camera's expose signal.
    """
    print(f"Programming PLogic using Preset {PLOGIC_LASER_PRESET_NUM}...")

    # Step 1: Apply the preset to configure BNC routing.
    # The command is [Addr#]CCA X=<preset #>
    _execute_tiger_serial_command(f"{PLOGIC_LABEL[-2:]}CCA X={PLOGIC_LASER_PRESET_NUM}")

    # Step 2: Link the master "laser on" cell (Cell 10) to the camera's expose signal.
    # This makes the laser trigger follow the camera exposure.
    print(
        f"Linking master laser cell ({PLOGIC_LASER_ON_CELL}) to camera expose signal ({PLOGIC_LASER_TRIGGER_TTL_ADDR})..."
    )
    # M E=cell_addr -> Select cell to edit
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    # CCA Z=source_addr -> Route the source to the cell's input
    _execute_tiger_serial_command(f"CCA Z={PLOGIC_LASER_TRIGGER_TTL_ADDR}")

    print("PLogic laser control configured.")


def reset_plogic_outputs():
    """
    Resets the master laser cell to be off. The BNC outputs will follow.
    """
    print("Resetting PLogic master laser cell to OFF...")
    _execute_tiger_serial_command(f"M E={PLOGIC_LASER_ON_CELL}")
    _execute_tiger_serial_command("CCA Z=0")  # Set input to ground (always off)
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


# --- Device Configuration and Control ---
def configure_devices_for_slice_scan(
    galvo_slice_amplitude_deg,
    galvo_slice_center_deg,
    piezo_fixed_position_um,
    num_slices_ctrl,
):
    """Configures Galvo, Piezo, and PLogic for the SPIM acquisition."""
    print("Preparing controller for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "Yes")

    # Use the new, preset-based PLogic configuration
    configure_plogic_for_laser_control_with_preset()

    # Galvo Device Configuration
    set_property(GALVO_A_LABEL, "SPIMNumSlicesPerPiezo", 1)
    set_property(GALVO_A_LABEL, "SPIMDelayBeforeRepeat(ms)", 0.0)
    set_property(GALVO_A_LABEL, "SPIMNumRepeats", 1)
    set_property(GALVO_A_LABEL, "SPIMDelayBeforeSide(ms)", DELAY_BEFORE_SIDE_MS)
    set_property(
        GALVO_A_LABEL,
        "SPIMAlternateDirectionsEnable",
        "Yes" if SCAN_OPPOSITE_DIRECTIONS else "No",
    )
    set_property(GALVO_A_LABEL, "SPIMScanDuration(ms)", SCAN_PERIOD_MS)
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


if __name__ == "__main__":
    try:
        hw_main_interface = HardwareInterface(config_file_path=CFG_PATH)
        run_acquisition_sequence(hw_main_interface)
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        print("\nScript execution finished.")
