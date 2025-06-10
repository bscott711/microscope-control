from pymmcore_plus import CMMCorePlus
from typing import Optional, Dict
import traceback
import time
import os

# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- Global Constants and Configuration ---
# Default configuration file path - Ensure this is defined globally
CFG_PATH = "hardware_profiles/20250523-OPM.cfg"

# Property names for PLogic card
PLOGIC_SET_PRESET_PROP = "SetCardPreset"
PLOGIC_OUTPUT_STATE_PROP = "PLogicOutputState"
PLOGIC_MODE_PROP = "PLogicMode"
CAMERA_TRIGGER_MODE_PROP = "TriggerMode"  # Generic, may need camera-specific adaptation

# Define Parameters (Acquisition Settings) - these are also global for this script
NUM_SLICES_SETTING = 50
STEP_SIZE_UM = 1.0
PIEZO_CENTER_UM = -31.0
SLICE_CALIBRATION_SLOPE_UM_PER_DEG = 100.0
SLICE_CALIBRATION_OFFSET_UM = 0.0
CAMERA_MODE_IS_OVERLAP = False
SCAN_PERIOD_MS = 10.0
CAMERA_EXPOSURE_MS = 9.0
NUM_SIDES = 1
FIRST_SIDE_IS_A = True
SCAN_OPPOSITE_DIRECTIONS = False
DELAY_BEFORE_SIDE_MS = 50.0
SHEET_WIDTH_DEG = 0.5
SHEET_OFFSET_DEG = 0.0

# Device labels - Ensure these match your Micro-Manager configuration
GALVO_A_LABEL = "Scanner:AB:33"
PIEZO_A_LABEL = "PiezoStage:P:34"
CAMERA_A_LABEL = "Camera-1"  # Your camera label
PLOGIC_LABEL = "PLogic:E:36"  # Assuming you have a PLogic device label


# --- Helper Function to Set Device Properties (Global) ---
def set_property(device_label, property_name, value):
    if device_label not in mmc.getLoadedDevices():
        print(
            f"Warning: Device {device_label} not found in loaded configuration. Cannot set property '{property_name}'."
        )
        return
    if mmc.hasProperty(device_label, property_name):
        current_value_str = mmc.getProperty(device_label, property_name)
        try:
            if (
                isinstance(value, (int, float))
                and abs(float(current_value_str) - float(value)) < 1e-9
            ):
                return
        except ValueError:
            if current_value_str == str(value):
                return
        mmc.setProperty(device_label, property_name, value)
        # print(f"Set {device_label}.{property_name} = {value}")
    else:
        print(f"Warning: Device {device_label} does not have property {property_name}")


# --- Calculations Based on Settings (Global) ---
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


# --- Configure Devices for Acquisition (Global) ---
def configure_devices_for_slice_scan(
    galvo_slice_amplitude_deg,
    galvo_slice_center_deg,
    piezo_fixed_position_um,
    num_slices_ctrl,
):
    print("Preparing controller for SLICE_SCAN_ONLY on Side A...")
    # Ensure Beam is Enabled for the Galvo
    set_property(GALVO_A_LABEL, "BeamEnabled", "Yes")
    # PLogic SPIM "Running" Flag (Mimicking ASIdiSPIM's prepareControllerForAcquisition)
    if PLOGIC_LABEL in mmc.getLoadedDevices():
        set_property(PLOGIC_LABEL, PLOGIC_SET_PRESET_PROP, "3 - cell 1 high")

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
    set_property(
        GALVO_A_LABEL, "SingleAxisXAmplitude(deg)", SHEET_WIDTH_DEG
    )  # Sheet Width
    set_property(
        GALVO_A_LABEL, "SingleAxisXOffset(deg)", SHEET_OFFSET_DEG
    )  # Sheet X Offset

    # Piezo Device Configuration
    set_property(PIEZO_A_LABEL, "SingleAxisAmplitude(um)", 0.0)
    set_property(PIEZO_A_LABEL, "SingleAxisOffset(um)", piezo_fixed_position_um)
    set_property(PIEZO_A_LABEL, "SPIMNumSlices", num_slices_ctrl)
    set_property(PIEZO_A_LABEL, "SPIMState", "Armed")


# --- Trigger Acquisition (Global) ---
def trigger_slice_scan_acquisition():
    print("Triggering acquisition for SLICE_SCAN_ONLY on Side A...")
    set_property(GALVO_A_LABEL, "SPIMState", "Running")
    print("--- Acquisition Triggered ---")


# --- Wait for Acquisition to Complete (Global) ---
def wait_for_camera_acquisition(
    camera_label,
    num_images_expected,
    first_image_timeout_s=10.0,
    inter_image_timeout_s=5.0,
):
    print(
        f"Waiting for acquisition on {camera_label} (expecting {num_images_expected} images)..."
    )
    images_popped = 0
    wait_start_time = time.monotonic()
    first_image_arrived = False
    while time.monotonic() - wait_start_time < first_image_timeout_s:
        if mmc.getRemainingImageCount() > 0 or not mmc.isSequenceRunning(camera_label):
            first_image_arrived = True
            break
        time.sleep(0.005)

    if not first_image_arrived and mmc.isSequenceRunning(camera_label):
        print(
            f"Timeout: First image not received from {camera_label} within {first_image_timeout_s}s."
        )
        if mmc.isSequenceRunning(camera_label):
            mmc.stopSequenceAcquisition(camera_label)
        return images_popped

    last_image_pop_time = time.monotonic()
    while images_popped < num_images_expected:
        current_time = time.monotonic()
        if mmc.getRemainingImageCount() > 0:
            try:
                _ = mmc.popNextTaggedImage()  # Pop image, discard for this example
                images_popped += 1
                last_image_pop_time = current_time
            except Exception as e:
                print(f"Error popping image: {e}")
                break
        elif not mmc.isSequenceRunning(camera_label):
            if images_popped < num_images_expected:
                print(
                    f"Warning: Camera sequence on {camera_label} stopped early. Received {images_popped}/{num_images_expected}."
                )
            break
        else:
            if (current_time - last_image_pop_time) > inter_image_timeout_s:
                print(
                    f"Timeout: No new image from {camera_label} for {inter_image_timeout_s}s. Received {images_popped}/{num_images_expected}."
                )
                if mmc.isSequenceRunning(camera_label):
                    mmc.stopSequenceAcquisition(camera_label)
                break
            time.sleep(0.001)

    if images_popped == num_images_expected:
        print(f"Successfully acquired {images_popped} images from {camera_label}.")
    if mmc.isSequenceRunning(camera_label):
        print(f"Sequence on {camera_label} still running. Stopping...")
        mmc.stopSequenceAcquisition(camera_label)
    while mmc.getRemainingImageCount() > 0:
        try:
            mmc.popNextTaggedImage()
            print("Drained an unexpected image from buffer post-acquisition.")
        except Exception:
            break
    print("Finished waiting for acquisition.")
    return images_popped


# --- Post-Acquisition Cleanup (Global) ---
def cleanup_slice_scan_devices():
    print("Cleaning up controller for Side A...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "No")  # Turn beam off
    set_property(GALVO_A_LABEL, "SPIMState", "Idle")
    set_property(PIEZO_A_LABEL, "SingleAxisOffset(um)", PIEZO_CENTER_UM)
    set_property(PIEZO_A_LABEL, "SPIMState", "Idle")
    if PLOGIC_LABEL in mmc.getLoadedDevices():
        set_property(
            PLOGIC_LABEL, PLOGIC_SET_PRESET_PROP, "2 - cell 1 low"
        )  # Corresponds to acquisition not running
    print("--- Cleanup Complete ---")


# --- HardwareInterface Class (as provided by user, with minor corrections) ---
class HardwareInterface:
    # ... (Content of HardwareInterface class as provided by user, with hasDevice corrections) ...
    # Make sure its __init__ uses the global mmc instance, or pass it in.
    # For this script, it will use the global mmc.
    # Add camera trigger mode setting here if it's generic enough, or call externally.
    # For simplicity, camera trigger mode setting will be handled outside this class for now.
    # LASER_PRESETS and PLogic methods are part of this class.
    # For BNC1 (laser) to work dynamically with the scan, this class would need
    # methods to program PLogic cells, not just set static presets.

    # Presets for laser control via SetCardPreset property
    LASER_PRESETS: Dict[str, str] = {
        "L1_ON": "5 - BNC5 enabled",
        "L2_ON": "6 - BNC6 enabled",
        "L3_ON": "7 - BNC7 enabled",
        "L4_ON": "8 - BNC8 enabled",
        "ALL_ON": "30 - BNC5-BNC8 enabled",
        "ALL_OFF": "9 - BNC5-8 all disabled",
    }  # ... rest of HardwareInterface ...

    def __init__(self, config_file_path: Optional[str] = None):  # Changed arg name
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()
        self._set_default_stages()

    def _initialize_hardware(self):
        print("Initializing HardwareInterface...")
        current_loaded_config = ""
        try:
            current_loaded_config = mmc.systemConfigurationFile()
        except Exception as e:
            print(f"Note: Could not get initial system configuration file: {e}")

        target_config_to_load = self.config_path
        if target_config_to_load:
            if not os.path.isabs(target_config_to_load):
                # Try to resolve relative path more simply
                if os.path.exists(target_config_to_load):
                    target_config_to_load = os.path.abspath(target_config_to_load)
                else:  # Try relative to script if __file__ is defined
                    try:
                        script_dir = os.path.dirname(os.path.abspath(__file__))
                        path_from_script_dir = os.path.join(
                            script_dir, target_config_to_load
                        )
                        if os.path.exists(path_from_script_dir):
                            target_config_to_load = path_from_script_dir
                        else:  # Try relative to CWD as a last local resort
                            path_from_cwd = os.path.join(
                                os.getcwd(), target_config_to_load
                            )
                            if os.path.exists(path_from_cwd):
                                target_config_to_load = path_from_cwd
                            else:
                                print(
                                    f"Warning: Relative config path '{self.config_path}' not found. Trying as is."
                                )
                    except NameError:  # __file__ not defined (e.g. interactive)
                        path_from_cwd = os.path.join(os.getcwd(), target_config_to_load)
                        if os.path.exists(path_from_cwd):
                            target_config_to_load = os.path.abspath(path_from_cwd)
                        else:
                            print(
                                f"Warning: Relative config path '{self.config_path}' not found (and __file__ undefined). Trying as is."
                            )

            if (
                current_loaded_config
                and os.path.normcase(os.path.abspath(current_loaded_config))
                == os.path.normcase(os.path.abspath(target_config_to_load))
                and ("TigerCommHub" in mmc.getLoadedDevices())
            ):
                print(
                    f"Target configuration '{target_config_to_load}' is already loaded and seems valid."
                )
                self.config_path = target_config_to_load
            else:
                print(
                    f"Current config: '{current_loaded_config}'. Attempting to load target: '{target_config_to_load}'"
                )
                try:
                    mmc.loadSystemConfiguration(target_config_to_load)
                    # Verify loaded config path and presence of a key ASI device
                    loaded_config_file = mmc.systemConfigurationFile() or ""
                    if os.path.normcase(
                        os.path.abspath(loaded_config_file)
                    ) == os.path.normcase(os.path.abspath(target_config_to_load)) and (
                        "TigerCommHub" in mmc.getLoadedDevices()
                    ):
                        print(
                            f"Successfully loaded configuration: {target_config_to_load}"
                        )
                        self.config_path = target_config_to_load
                    else:
                        raise RuntimeError(
                            f"Failed to verify load of {target_config_to_load}. Current: {mmc.systemConfigurationFile()}, Loaded Devices: {mmc.getLoadedDevices()}"
                        )
                except Exception as e:
                    print(
                        f"CRITICAL Error loading specified configuration '{target_config_to_load}': {e}"
                    )
                    traceback.print_exc()
                    raise
        elif current_loaded_config and ("TigerCommHub" in mmc.getLoadedDevices()):
            print(
                f"No specific config path provided. Using existing MMCore config: {current_loaded_config}"
            )
            self.config_path = current_loaded_config
        else:
            msg = "HardwareInterface initialized without a config_path, and MMCore has no valid ASI configuration loaded."
            print(f"ERROR: {msg}")
            raise FileNotFoundError(msg)

        if not mmc.getLoadedDevices():
            print("WARNING: No devices seem to be loaded after initialization attempt!")
        else:
            print(
                f"HardwareInterface initialized. Effective config: {mmc.systemConfigurationFile()}"
            )

    def _set_default_stages(self):
        # Simplified for brevity, ensure these devices are in your config
        if self.xy_stage in mmc.getLoadedDevices():
            mmc.setXYStageDevice(self.xy_stage)
        if self.main_z_objective in mmc.getLoadedDevices():
            mmc.setFocusDevice(self.main_z_objective)

    @property
    def xy_stage(self) -> str:
        return "XYStage:XY:31"

    @property
    def main_z_objective(self) -> str:
        return "ZStage:Z:32"

    @property
    def galvo_scanner(self) -> str:
        return GALVO_A_LABEL  # Use global constant

    @property
    def crisp_o3_piezo_stage(self) -> str:
        return PIEZO_A_LABEL  # Use global constant

    @property
    def plogic_lasers(self) -> str:
        return PLOGIC_LABEL  # Use global constant

    @property
    def camera1(self) -> str:
        return CAMERA_A_LABEL  # Use global constant

    def set_camera_trigger_mode(
        self, camera_label: str, mode: str, active_edge_level: Optional[str] = None
    ) -> bool:
        """Sets the trigger mode of the specified camera."""
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Camera device '{camera_label}' not found.")
            return False
        try:
            # Try generic property first (e.g. for Andor, PVCAM, PCO)
            if mmc.hasProperty(camera_label, CAMERA_TRIGGER_MODE_PROP):
                allowed_modes = mmc.getAllowedPropertyValues(
                    camera_label, CAMERA_TRIGGER_MODE_PROP
                )
                if mode not in allowed_modes:
                    print(
                        f"Error: Mode '{mode}' not allowed for {camera_label} via '{CAMERA_TRIGGER_MODE_PROP}'. Allowed: {list(allowed_modes)}"
                    )
                    return False
                current_mode = mmc.getProperty(camera_label, CAMERA_TRIGGER_MODE_PROP)
                if current_mode != mode:
                    mmc.setProperty(camera_label, CAMERA_TRIGGER_MODE_PROP, mode)
                print(f"Set {camera_label} '{CAMERA_TRIGGER_MODE_PROP}' to '{mode}'.")
                return True
            # Kinetix22 specific handling (example)
            elif mmc.hasProperty(camera_label, "TRIGGER SOURCE"):
                print(f"Using Kinetix specific trigger properties for {camera_label}")
                # Mode will be for TRIGGER SOURCE Allowed: ['Edge Trigger', 'Internal Trigger', 'Level Trigger', 'Level Trigger Overlap', 'Software Trigger Edge', 'Software Trigger First', 'Trigger First']
                allowed_sources = mmc.getAllowedPropertyValues(
                    camera_label, "TRIGGER SOURCE"
                )
                if mode not in allowed_sources:
                    print(
                        f"Error: Mode '{mode}' not allowed for {camera_label} TRIGGER SOURCE. Allowed: {list(allowed_sources)}"
                    )
                    return False
                if mmc.getProperty(camera_label, "TRIGGER SOURCE") != mode:
                    mmc.setProperty(camera_label, "TRIGGER SOURCE", mode)
                print(f"Set {camera_label} TRIGGER SOURCE to '{mode}'.")

                if active_edge_level and mmc.hasProperty(
                    camera_label, "TRIGGER ACTIVE"
                ):
                    allowed_active = mmc.getAllowedPropertyValues(
                        camera_label, "TRIGGER ACTIVE"
                    )
                    if active_edge_level not in allowed_active:
                        print(
                            f"Error: Mode '{active_edge_level}' not allowed for {camera_label} TRIGGER ACTIVE. Allowed: {list(allowed_active)}"
                        )
                        return False
                    if (
                        mmc.getProperty(camera_label, "TRIGGER ACTIVE")
                        != active_edge_level
                    ):
                        mmc.setProperty(
                            camera_label, "TRIGGER ACTIVE", active_edge_level
                        )
                    print(
                        f"Set {camera_label} TRIGGER ACTIVE to '{active_edge_level}'."
                    )
                return True
            else:
                print(
                    f"Error: Camera '{camera_label}' does not have a known trigger mode property ('{CAMERA_TRIGGER_MODE_PROP}' or Hamamatsu specific)."
                )
                return False
        except Exception as e:
            print(f"Error setting trigger mode for {camera_label} to '{mode}': {e}")
            return False

    # ... (other methods from user's HardwareInterface class like set_laser_preset, etc.) ...
    # Add other methods from your HardwareInterface class here


# --- Main Script Execution ---
def run_acquisition_sequence(hw_interface: HardwareInterface):
    """Orchestrates the SLICE_SCAN_ONLY acquisition."""
    galvo_amp_deg, galvo_center_deg, num_slices_for_ctrl = calculate_galvo_parameters()
    piezo_fixed_pos_um = round(PIEZO_CENTER_UM, 3)

    try:
        # 1. Set Active Camera in MMCore
        print(f"Setting active camera in MMCore to: {hw_interface.camera1}")
        mmc.setCameraDevice(hw_interface.camera1)

        # 2. Configure Camera for External Triggering
        print(f"Configuring {hw_interface.camera1} for external triggering...")

        if not hw_interface.set_camera_trigger_mode(
            hw_interface.camera1, "Edge Trigger"
        ):
            print(
                f"Failed to set {hw_interface.camera1} to external trigger mode. Aborting."
            )
            return

        # 3. Configure ASI Devices (Galvo and Piezo for SPIM)
        configure_devices_for_slice_scan(
            galvo_amp_deg, galvo_center_deg, piezo_fixed_pos_um, num_slices_for_ctrl
        )

        # 4. Prepare Camera for Hardware Sequence Acquisition
        print(f"Setting exposure on {hw_interface.camera1} to {CAMERA_EXPOSURE_MS} ms")
        mmc.setExposure(hw_interface.camera1, CAMERA_EXPOSURE_MS)

        print("Initializing circular buffer...")
        mmc.initializeCircularBuffer()  # Clears and then initializes

        print(
            f"Starting camera sequence acquisition on {hw_interface.camera1} for {num_slices_for_ctrl} images."
        )
        # numImages, intervalMs (0 for hardware triggering), stopOnOverflow (true)
        mmc.startSequenceAcquisition(hw_interface.camera1, num_slices_for_ctrl, 0, True)

        # 5. Trigger Acquisition (Start Galvo Scan on ASI Controller)
        trigger_slice_scan_acquisition()

        # 6. Wait for Acquisition to Complete (and pop images from buffer)
        images_acquired = wait_for_camera_acquisition(
            hw_interface.camera1, num_slices_for_ctrl
        )
        print(f"Main acquisition block finished. Popped {images_acquired} images.")

    except ValueError as ve:
        print(f"Configuration error in SLICE_SCAN_ONLY sequence: {ve}")
    except Exception as e:
        print(f"An error occurred during SLICE_SCAN_ONLY sequence: {e}")
        traceback.print_exc()
        if mmc.isSequenceRunning(hw_interface.camera1):
            try:
                mmc.stopSequenceAcquisition(hw_interface.camera1)
                print(
                    f"Stopped camera sequence on {hw_interface.camera1} due to error."
                )
            except Exception as e_stop:
                print(
                    f"Error trying to stop camera sequence during error handling: {e_stop}"
                )
    finally:
        # 7. Cleanup devices
        cleanup_slice_scan_devices()
        # Optionally restore original camera trigger mode
        # print(f"Attempting to restore {hw_interface.camera1} trigger mode to Internal (example)...")
        # hw_interface.set_camera_trigger_mode(hw_interface.camera1, "Internal")


if __name__ == "__main__":
    hw_main_interface = None
    try:
        # Use the global CFG_PATH for initialization
        hw_main_interface = HardwareInterface(config_file_path=CFG_PATH)
        run_acquisition_sequence(hw_main_interface)
    except FileNotFoundError as e_fnf:
        print(f"Initialization failed due to config file issue: {e_fnf}")
    except (
        RuntimeError
    ) as e_rt:  # Catch potential runtime errors from CMMCorePlus/MMCore
        print(f"Runtime error during script execution: {e_rt}")
        traceback.print_exc()
    except Exception as e_main:
        print(f"An unexpected error occurred in __main__: {e_main}")
        traceback.print_exc()
    finally:
        # if hw_main_interface:
        #     hw_main_interface.shutdown_hardware(reset_core=False) # Optional
        print("\nScript execution finished.")
