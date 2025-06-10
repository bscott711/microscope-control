import time
from typing import Optional, List
import os
import traceback
from pymmcore_plus import CMMCorePlus

# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- Global Constants and Configuration ---
CFG_PATH = "hardware_profiles/20250523-OPM.cfg"

# --- Device Labels ---
CAMERA_A_LABEL = "Camera-1"
PLOGIC_LABEL = "PLogic:E:36"
TIGER_COMM_HUB_LABEL = "TigerCommHub"
GALVO_A_LABEL = "Scanner:AB:33"

# --- PLogic Signal Address Constants ---
# --- Input Sources ---
PLOGIC_GROUND_ADDR = 0  # Always LOW signal
PLOGIC_CAMERA_TRIGGER_TTL_ADDR = 44  # Camera Trigger signal (from TTL-4)
PLOGIC_4KHZ_CLOCK_ADDR = 192  # Internal 4kHz evaluation clock

# --- Physical Output Addresses ---
PLOGIC_BNC5_ADDR = 37  # Address for physical BNC port 5

# --- Internal Cell Addresses ---
# Using a 'scratch' cell for our custom logic to avoid conflicts
PLOGIC_TIMER_CELL = 7

# --- Acquisition Settings ---
CAMERA_EXPOSURE_MS = 9.0
SCAN_PERIOD_MS = 10.0
NUM_SLICES_SETTING = 50
STEP_SIZE_UM = 1.0
PIEZO_CENTER_UM = -31.0
SLICE_CALIBRATION_SLOPE_UM_PER_DEG = 100.0
# ... other settings can be added here ...


# --- Low-Level Helper Functions ---
def _execute_tiger_serial_command(command_string: str):
    """Sends a raw serial command to the Tiger controller via the CommHub."""
    original_setting = mmc.getProperty(
        TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "No")

    mmc.setProperty(TIGER_COMM_HUB_LABEL, "SerialCommand", command_string)

    if original_setting == "Yes":
        mmc.setProperty(TIGER_COMM_HUB_LABEL, "OnlySendSerialCommandOnChange", "Yes")

    time.sleep(0.02)  # Small delay for command to be processed


def set_property(device_label, property_name, value):
    """Sets a device property if it exists."""
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        mmc.setProperty(device_label, property_name, value)
    else:
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found."
        )


# --- Modular PLogic Programming Functions ---
def program_logic_cell(
    cell_address: int,
    cell_type: int,
    config_value: int,
    input_x: int = 0,
    input_y: int = 0,
    input_z: int = 0,
    input_f: int = 0,
):
    """
    Programs a single PLogic cell with its type, configuration, and inputs.
    This directly mirrors the 'Logic Cells' tab in the GUI.

    :param cell_address: The address of the cell to program (1-16).
    :param cell_type: The numeric code for the cell type (e.g., 14 for one-shot).
    :param config_value: The configuration value for the cell (e.g., duration).
    :param input_x: The source address for the first input (CCB X).
    :param input_y: The source address for the second input (CCB Y).
    :param input_z: The source address for the third input (CCB Z).
    :param input_f: The source address for the fourth input (CCB F).
    """
    print(f"Programming Logic Cell {cell_address}...")
    # Select the cell for editing
    _execute_tiger_serial_command(f"M E={cell_address}")
    # Set the cell type (resets the cell)
    _execute_tiger_serial_command(f"CCA Y={cell_type}")
    # Set the cell configuration
    if config_value is not None:
        _execute_tiger_serial_command(f"CCA Z={config_value}")
    # Set the cell inputs
    _execute_tiger_serial_command(
        f"CCB X={input_x} Y={input_y} Z={input_z} F={input_f}"
    )


def route_signal_to_physical_output(output_address: int, source_address: int):
    """
    Routes an internal signal to a physical BNC or TTL output.
    This directly mirrors the 'Physical I/O' tab in the GUI.

    :param output_address: The address of the physical port (e.g., 37 for BNC5).
    :param source_address: The address of the internal signal to route (e.g., 7 for Cell 7).
    """
    print(f"Routing Source {source_address} to Physical Output {output_address}...")
    # Select the physical output port for editing
    _execute_tiger_serial_command(f"M E={output_address}")
    # Set its source address
    _execute_tiger_serial_command(f"CCA Z={source_address}")


# --- High-Level PLogic Configuration ---
def setup_laser_one_shot_pulse():
    """
    High-level function to configure a one-shot laser pulse on BNC5.
    """
    print("Configuring PLogic for one-shot laser pulse on BNC5...")

    # Calculate the required pulse duration in 4kHz clock cycles
    pulses_per_ms = 4
    pulse_duration_cycles = int(CAMERA_EXPOSURE_MS * pulses_per_ms)

    # Program our 'scratch' cell to be a one-shot timer
    program_logic_cell(
        cell_address=PLOGIC_TIMER_CELL,
        cell_type=14,  # one-shot (non-retriggerable)
        config_value=pulse_duration_cycles,
        input_x=PLOGIC_CAMERA_TRIGGER_TTL_ADDR,  # Trigger
        input_y=PLOGIC_4KHZ_CLOCK_ADDR,  # Clock
    )

    # Route the output of our timer cell to the physical BNC port
    route_signal_to_physical_output(
        output_address=PLOGIC_BNC5_ADDR, source_address=PLOGIC_TIMER_CELL
    )

    print(
        f"PLogic configured. BNC5 will output a {CAMERA_EXPOSURE_MS}ms pulse on camera trigger."
    )


def reset_laser_output_to_ground():
    """Resets the laser output BNC to be off."""
    print("Resetting BNC5 to ground...")
    route_signal_to_physical_output(
        output_address=PLOGIC_BNC5_ADDR, source_address=PLOGIC_GROUND_ADDR
    )


# --- Device Configuration and Main Sequence (Simplified for Demonstration) ---
def configure_devices_for_acquisition():
    """Sets up all devices for the acquisition sequence."""
    print("Preparing controller for acquisition...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "Yes")
    setup_laser_one_shot_pulse()
    # ... other device configurations (galvo scan params, etc.) would go here ...


def cleanup_devices():
    """Resets all devices after the acquisition."""
    print("Cleaning up devices...")
    set_property(GALVO_A_LABEL, "BeamEnabled", "No")
    reset_laser_output_to_ground()
    # ... other device cleanup ...


# --- HardwareInterface Class ---
class HardwareInterface:
    """A simplified class to manage hardware initialization."""

    def __init__(self, config_file_path: Optional[str] = None):
        self._initialize_hardware(config_file_path)

    def _initialize_hardware(self, config_file_path):
        print("Initializing HardwareInterface...")
        if not config_file_path:
            raise ValueError("Configuration file path is required.")

        target_config = os.path.abspath(config_file_path)
        if not os.path.exists(target_config):
            raise FileNotFoundError(f"Configuration file not found at: {target_config}")

        current_config = mmc.systemConfigurationFile()
        # FIX: Check if current_config is None before comparing
        if not current_config or os.path.normcase(current_config) != os.path.normcase(
            target_config
        ):
            print(f"Loading system configuration: {target_config}")
            mmc.loadSystemConfiguration(target_config)
        else:
            print("Correct configuration already loaded.")

    def find_and_set_trigger_mode(
        self, camera_label: str, desired_modes: List[str]
    ) -> bool:
        """Finds and sets the camera's trigger mode."""
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            print(f"Error: Camera '{camera_label}' has no '{trigger_prop}' property.")
            return False

        allowed = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
        for mode in desired_modes:
            if mode in allowed:
                set_property(camera_label, trigger_prop, mode)
                print(f"Set {camera_label} TriggerMode to '{mode}'.")
                return True

        print(f"Error: Could not set desired trigger mode. Allowed: {list(allowed)}")
        return False


# --- Main Script Execution ---
def main():
    """Main execution block."""
    hw_interface = None
    try:
        hw_interface = HardwareInterface(config_file_path=CFG_PATH)

        # 1. Configure Camera
        external_modes = [
            "Edge Trigger",
        ]
        if not hw_interface.find_and_set_trigger_mode(CAMERA_A_LABEL, external_modes):
            return  # Abort if camera cannot be configured

        # 2. Configure Controller (including PLogic)
        configure_devices_for_acquisition()

        # 3. Run Acquisition
        print("\n--- Starting mock acquisition ---")
        mmc.setExposure(CAMERA_A_LABEL, CAMERA_EXPOSURE_MS)
        mmc.startSequenceAcquisition(CAMERA_A_LABEL, NUM_SLICES_SETTING, 0, True)

        # This would be where you trigger the hardware (e.g., galvo scan)
        print(">>> Hardware triggered. Acquisition running... (simulating for 2s)")
        time.sleep(2)

        if mmc.isSequenceRunning():
            mmc.stopSequenceAcquisition()
        print("--- Mock acquisition finished ---\n")

    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
    finally:
        # 4. Cleanup
        if "TigerCommHub" in mmc.getLoadedDevices():
            cleanup_devices()
            internal_modes = ["Internal", "Internal Trigger"]
            if hw_interface is not None:
                hw_interface.find_and_set_trigger_mode(CAMERA_A_LABEL, internal_modes)
        print("\nScript execution finished.")


if __name__ == "__main__":
    main()
