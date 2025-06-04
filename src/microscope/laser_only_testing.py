from pymmcore_plus import CMMCorePlus
from typing import Optional, Dict, Union
import traceback
import time
import os

# Initialize global core instance
mmc = CMMCorePlus.instance()

# Property names for PLogic card
PLOGIC_SET_PRESET_PROP = "SetCardPreset"
PLOGIC_OUTPUT_STATE_PROP = "PLogicOutputState"
PLOGIC_MODE_PROP = "PLogicMode"


class LaserController:
    """
    A class to interface specifically with the PLogic laser hardware
    via pymmcore-plus. Uses a global CMMCorePlus instance.
    """

    # Presets for laser control via SetCardPreset property
    # Updated to use the full string labels as reported by getAllowedPropertyValues
    LASER_PRESETS: Dict[str, str] = {
        "L1_ON": "5 - BNC5 enabled",
        "L2_ON": "6 - BNC6 enabled",
        "L3_ON": "7 - BNC7 enabled",
        "L4_ON": "8 - BNC8 enabled",
        "ALL_ON": "30 - BNC5-BNC8 enabled",
        "ALL_OFF": "9 - BNC5-8 all disabled",
    }

    # For interpreting PLogicOutputState if it's used/readable and relevant
    _BITMASK_LASER_STATES: Dict[str, int] = {
        "OFF": 0,
        "L1": 1,
        "L2": 2,
        "L3": 4,
        "L4": 8,
        "L1_L2": 3,
        "L1_L3": 5,
        "L1_L4": 9,
        "L2_L3": 6,
        "L2_L4": 10,
        "L3_L4": 12,
        "L1_L2_L3": 7,
        "L1_L2_L4": 11,
        "L1_L3_L4": 13,
        "L2_L3_L4": 14,
        "ALL_ON_BITMASK": 15,
    }
    _INT_TO_BITMASK_LASER_STATE_NAME: Dict[int, str] = {
        v: k for k, v in _BITMASK_LASER_STATES.items()
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initializes the LaserController.

        Args:
            config_path: Optional path to a Micro-Manager configuration file.
                         If provided, this config will be loaded if no config or a
                         different config is already loaded in the global mmc instance.
                         If None, the interface will use the existing configuration
                         in the global mmc instance, or raise an error if none is loaded.
        """
        self.config_path: Optional[str] = config_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        """
        Ensures a Micro-Manager configuration is loaded and the PLogic device is present.
        """
        print("Initializing LaserController...")
        current_loaded_config = ""
        try:
            current_loaded_config = mmc.systemConfigurationFile()
        except Exception as e:
            print(f"Note: Could not get initial system configuration file: {e}")

        target_config_to_load = self.config_path

        if target_config_to_load:
            # Ensure the path is absolute for robust loading
            if not os.path.isabs(target_config_to_load):
                script_dir = os.path.dirname(__file__)
                potential_path_from_src_parent = os.path.join(
                    script_dir, "..", "..", target_config_to_load
                )
                potential_path_from_cwd = target_config_to_load

                if os.path.exists(potential_path_from_src_parent):
                    target_config_to_load = os.path.abspath(
                        potential_path_from_src_parent
                    )
                    print(f"Resolved relative config path to: {target_config_to_load}")
                elif os.path.exists(potential_path_from_cwd):
                    target_config_to_load = os.path.abspath(potential_path_from_cwd)
                    print(
                        f"Resolved relative config path (from CWD) to: {target_config_to_load}"
                    )
                else:
                    print(
                        f"Warning: Relative config path '{self.config_path}' not found easily. Trying as is."
                    )

            # Check if target config is already loaded and PLogic is present
            if current_loaded_config == target_config_to_load and (
                self.plogic_lasers in mmc.getLoadedDevices()
            ):
                print(
                    f"Target configuration '{target_config_to_load}' is already loaded and PLogic device '{self.plogic_lasers}' is present."
                )
            else:
                print(
                    f"Current config is '{current_loaded_config}'. Attempting to load target: '{target_config_to_load}'"
                )
                try:
                    mmc.loadSystemConfiguration(target_config_to_load)
                    # Verify load and PLogic device presence
                    if mmc.systemConfigurationFile() == target_config_to_load and (
                        self.plogic_lasers in mmc.getLoadedDevices()
                    ):
                        print(
                            f"Successfully loaded configuration: {target_config_to_load}"
                        )
                        self.config_path = (
                            target_config_to_load  # Ensure stored path is correct
                        )
                    else:
                        raise RuntimeError(
                            f"Failed to verify load of {target_config_to_load} or PLogic device '{self.plogic_lasers}' not found after load. Current config: {mmc.systemConfigurationFile()}, Loaded devices: {mmc.getLoadedDevices()}"
                        )
                except Exception as e:
                    print(
                        f"CRITICAL Error loading specified configuration '{target_config_to_load}': {e}"
                    )
                    traceback.print_exc()
                    raise  # Re-raise the exception to indicate critical failure
        else:  # No specific config_path provided to __init__
            if current_loaded_config and (self.plogic_lasers in mmc.getLoadedDevices()):
                print(
                    f"No specific config path provided to LaserController. Using existing MMCore config: {current_loaded_config}"
                )
                self.config_path = current_loaded_config  # Store the existing path
            else:
                msg = (
                    "LaserController initialized without a config_path, and "
                    f"MMCore has no valid configuration with PLogic device '{self.plogic_lasers}'."
                )
                print(f"ERROR: {msg}")
                raise FileNotFoundError(msg)

        if self.plogic_lasers not in mmc.getLoadedDevices():
            msg = f"CRITICAL Error: PLogic device '{self.plogic_lasers}' not found after initialization."
            print(msg)
            raise RuntimeError(msg)

        print(
            f"LaserController initialized. Effective config: {mmc.systemConfigurationFile()}"
        )
        print(f"PLogic device found: {self.plogic_lasers}")

    @property
    def plogic_lasers(self) -> str:
        return "PLogic:E:36"  # Assuming this is the correct label from your config

    def get_plogic_mode(self) -> Optional[str]:
        """Gets the current PLogicMode."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return None
        try:
            return mmc.getProperty(self.plogic_lasers, PLOGIC_MODE_PROP)
        except Exception as e:
            print(f"Error getting PLogicMode: {e}")
            traceback.print_exc()
            return None

    def set_plogic_mode(self, mode: str) -> bool:
        """Sets the PLogicMode. Note: Some modes are pre-init properties."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return False
        try:
            allowed_modes = mmc.getAllowedPropertyValues(
                self.plogic_lasers, PLOGIC_MODE_PROP
            )
            if mode not in allowed_modes:
                print(
                    f"Error: Mode '{mode}' not in allowed PLogicModes {allowed_modes} for {self.plogic_lasers}."
                )
                return False
            mmc.setProperty(self.plogic_lasers, PLOGIC_MODE_PROP, mode)
            print(f"Set PLogicMode for {self.plogic_lasers} to '{mode}'")
            time.sleep(0.1)  # Give device time to switch mode
            return True
        except RuntimeError as e_rt:
            if "Cannot set pre-init property after initialization" in str(e_rt):
                print(
                    f"Info: PLogicMode ('{mode}') is a pre-init property and cannot be changed after system load. Current mode: {self.get_plogic_mode()}"
                )
                return False
            else:
                print(f"Runtime Error setting PLogicMode to '{mode}': {e_rt}")
                traceback.print_exc()
                return False
        except Exception as e:
            print(f"Error setting PLogicMode to '{mode}': {e}")
            traceback.print_exc()
            return False

    def set_laser_preset(self, preset_name_or_value: Union[str, int]) -> bool:
        """Sets the PLogic card to a pre-defined preset using its string label or number."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return False

        preset_string_to_set: Optional[str] = None  # Property expects string
        descriptive_name = str(preset_name_or_value)

        if isinstance(preset_name_or_value, str):
            # If a key like "L1_ON" is given, look up its string value
            if preset_name_or_value.upper() in self.LASER_PRESETS:
                preset_string_to_set = self.LASER_PRESETS[preset_name_or_value.upper()]
                descriptive_name = (
                    f"{preset_name_or_value.upper()} ('{preset_string_to_set}')"
                )
            else:  # Assume it might be the direct string label of a preset
                # Check if it's an allowed value before trying to set
                try:
                    allowed_presets = mmc.getAllowedPropertyValues(
                        self.plogic_lasers, PLOGIC_SET_PRESET_PROP
                    )
                    if preset_name_or_value in allowed_presets:
                        preset_string_to_set = preset_name_or_value
                        descriptive_name = f"'{preset_string_to_set}' (direct string)"
                    else:
                        print(
                            f"Error: Direct string preset '{preset_name_or_value}' not in allowed values: {allowed_presets}"
                        )
                        return False
                except Exception as e_allowed:
                    print(
                        f"Error checking allowed presets for '{preset_name_or_value}': {e_allowed}"
                    )
                    return False

        elif isinstance(preset_name_or_value, int):
            # If an int is given, assume it's a preset number and convert to string for setProperty
            # Also try to find its descriptive name for logging
            try:
                allowed_presets = mmc.getAllowedPropertyValues(
                    self.plogic_lasers, PLOGIC_SET_PRESET_PROP
                )
                # Find the full string value that starts with the integer number
                found_preset_string = None
                for ap in allowed_presets:
                    if ap.startswith(str(preset_name_or_value) + " -"):
                        found_preset_string = ap
                        break

                if found_preset_string:
                    preset_string_to_set = found_preset_string
                    descriptive_name = (
                        f"PRESET_NUM_{preset_name_or_value} ('{preset_string_to_set}')"
                    )
                else:
                    print(
                        f"Error: Preset number {preset_name_or_value} does not match the start of any allowed preset strings: {allowed_presets}"
                    )
                    return False
            except Exception as e:
                print(
                    f"Error finding string for preset number {preset_name_or_value}: {e}"
                )
                return False
        else:
            print(
                f"Error: Invalid type for laser preset: {type(preset_name_or_value)}. Must be str or int."
            )
            return False

        if preset_string_to_set is None:
            print(
                f"Error: Could not determine preset string for: {preset_name_or_value}"
            )
            return False

        try:
            # Ensure the value being sent is a string, as per getAllowedPropertyValues output
            mmc.setProperty(
                self.plogic_lasers, PLOGIC_SET_PRESET_PROP, preset_string_to_set
            )
            print(f"Set PLogic ({self.plogic_lasers}) to preset: {descriptive_name}")
            time.sleep(0.1)  # Give device time to apply preset
            return True
        except Exception as e:
            print(
                f"Error setting PLogic '{self.plogic_lasers}' prop '{PLOGIC_SET_PRESET_PROP}' to '{preset_string_to_set}': {e}"
            )
            traceback.print_exc()
            return False

    def get_laser_output_state(self) -> Optional[Dict[str, Union[int, str]]]:
        """Reads PLogicOutputState. Its value is dependent on PLogicMode."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return None
        try:
            val_str = mmc.getProperty(self.plogic_lasers, PLOGIC_OUTPUT_STATE_PROP)
            try:
                val_int = int(val_str)
                name = self._INT_TO_BITMASK_LASER_STATE_NAME.get(
                    val_int, f"BITMASK_VAL_{val_int}"
                )
                return {"value": val_int, "name": name, "raw_string": val_str}
            except ValueError:
                # Return raw string if it's not an integer (e.g., "Not available")
                return {"value": -1, "name": "NON_INTEGER_STATE", "raw_string": val_str}
        except Exception as e:
            print(f"Error getting PLogic prop '{PLOGIC_OUTPUT_STATE_PROP}': {e}")
            return None

    def shutdown_hardware(self, reset_core: bool = True):
        """Shuts down the hardware interface."""
        print("Shutting down laser controller...")
        if reset_core:
            print("Resetting MMCore (unloads all devices and resets core state).")
            mmc.reset()
        else:
            print("Unloading all devices (core state might persist).")
            mmc.unloadAllDevices()
        print("Hardware shutdown complete.")


def run_laser_tests(laser_controller: LaserController):
    """
    Runs a simple test sequence for the lasers using presets.
    """
    print("\n--- Running Simple Laser Tests via Presets ---")

    # Get initial state
    initial_mode = laser_controller.get_plogic_mode()
    print(f"Initial PLogicMode: {initial_mode if initial_mode is not None else 'N/A'}")
    initial_output_state = laser_controller.get_laser_output_state()
    print(
        f"Initial PLogicOutputState: {initial_output_state if initial_output_state is not None else 'N/A'}"
    )

    # Define test sequence using the keys from LASER_PRESETS
    test_sequence = [
        "L1_ON",
        "ALL_OFF",
        "L2_ON",
        "ALL_OFF",
        "L3_ON",
        "ALL_OFF",
        "L4_ON",
        "ALL_OFF",
        "ALL_ON",
        "ALL_OFF",
    ]

    # Attempt to set PLogicMode to one that supports presets if not already set.
    # Based on your config, "diSPIM Shutter" or similar might be needed.
    # We'll check allowed modes and try a common one if the initial isn't suitable.
    # Note: Changing PLogicMode might be a pre-init property, so this might fail
    # if the core was already initialized with a different mode.
    target_preset_mode = "diSPIM Shutter"  # Example mode from config
    mode_changed = False

    if initial_mode != target_preset_mode:
        print(
            f"\nAttempting to set PLogicMode to '{target_preset_mode}' for preset testing..."
        )
        if laser_controller.set_plogic_mode(target_preset_mode):
            mode_changed = True
        else:
            print(
                f"Warning: Could not set PLogicMode to '{target_preset_mode}'. Preset tests may fail if current mode is incompatible."
            )

    # Run the test sequence
    for preset_key in test_sequence:
        descriptive_name = preset_key  # Use key as name if not found in LASER_PRESETS
        if preset_key.upper() in laser_controller.LASER_PRESETS:
            descriptive_name = f"{preset_key.upper()} ('{laser_controller.LASER_PRESETS[preset_key.upper()]}')"

        print(f"\nSetting preset: {descriptive_name}")
        success = laser_controller.set_laser_preset(preset_key)

        if success:
            time.sleep(0.5)  # Allow time for the preset to activate
            current_output_state = laser_controller.get_laser_output_state()
            if current_output_state:
                print(
                    f"  PLogicOutputState after setting: Value={current_output_state.get('value')}, Raw='{current_output_state.get('raw_string')}'"
                )
            else:
                print("  Could not read PLogicOutputState.")
        else:
            print(f"  Failed to set preset: {descriptive_name}")

    print("\n--- Simple Laser Tests Complete ---")

    # Restore original mode if it was changed
    if mode_changed and initial_mode is not None:
        print(f"\nAttempting to restore PLogicMode to original: '{initial_mode}'...")
        laser_controller.set_plogic_mode(
            initial_mode
        )  # Note: This might fail if initial_mode was pre-init


# --- Example Usage ---
if __name__ == "__main__":
    print("Running Laser Only Diagnostic Test...")
    # Use a path relative to the project root, assuming this script is in src/microscope
    cfg_path = "hardware_profiles/20250523-OPM.cfg"

    laser_ctrl = None
    original_plogic_mode_at_start = None

    try:
        # Initialize the laser controller
        laser_ctrl = LaserController(config_path=cfg_path)

        # Store the mode before running tests, in case the test changes it
        original_plogic_mode_at_start = laser_ctrl.get_plogic_mode()

        # Run the simple laser tests
        run_laser_tests(laser_ctrl)

    except FileNotFoundError as e:
        print(f"Initialization failed due to missing or unconfirmed configuration: {e}")
    except RuntimeError as e:
        print(f"Initialization failed due to missing PLogic device: {e}")
    except Exception as e:
        print(f"An error occurred during diagnostic test: {e}")
        traceback.print_exc()
    finally:
        if laser_ctrl:
            # Ensure lasers are turned off at the end
            print(
                "\nEnsuring all lasers are OFF in finally block (using ALL_OFF preset)..."
            )
            if not laser_ctrl.set_laser_preset("ALL_OFF"):
                print("  Warning: Failed to set ALL_OFF preset in finally block.")
            else:
                final_output_state = laser_ctrl.get_laser_output_state()
                if final_output_state:
                    print(
                        f"  Final PLogicOutputState: Value={final_output_state.get('value')}, Raw='{final_output_state.get('raw_string')}'"
                    )
                else:
                    print(
                        "  Could not read final PLogicOutputState after attempting to set ALL_OFF preset."
                    )

            # Note: We don't automatically shutdown_hardware here
            # because other parts of the application (like Napari) might be using MMCore.
            # If running this script standalone and you want a full cleanup,
            # uncomment the line below:
            # laser_ctrl.shutdown_hardware(reset_core=True)

        print("\nLaser Only Diagnostic Test finished.")
