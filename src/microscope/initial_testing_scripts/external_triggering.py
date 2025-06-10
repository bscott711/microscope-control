from pymmcore_plus import CMMCorePlus, DeviceType  # Import DeviceType directly
from typing import Optional, Dict, Tuple, Any, Union
import traceback
import time  # Added for time.sleep in set_crisp_state and movement tests
import os  # For path joining if needed
import tifffile  # Added for saving images
import numpy as np  # Added for stacking multi-camera images

# Initialize global core instance
mmc = CMMCorePlus.instance()

# Property names for PLogic card
PLOGIC_SET_PRESET_PROP = "SetCardPreset"
PLOGIC_OUTPUT_STATE_PROP = "PLogicOutputState"
PLOGIC_FRONTAPANEL_OUTPUT_PROP = "FrontpanelOutputState"  # New property to test
PLOGIC_OUTPUT_CHANNEL_PROP = (
    "OutputChannel"  # Property to select a single channel in some modes
)
PLOGIC_MODE_PROP = "PLogicMode"
PLOGIC_POINTER_POSITION_PROP = "PointerPosition"
PLOGIC_EDIT_CELL_CONFIG_PROP = "EditCellConfig"
PLOGIC_SAVE_SETTINGS_PROP = "SaveCardSettings"
PLOGIC_VAL_SAVE_SETTINGS = "Z - save settings to card (partial)"  # From user snippet

PLOGIC_CELL_ADDR_ALWAYS_LOW = 0  # PLogic cell 0 is typically GND/LOW
PLOGIC_CELL_ADDR_ALWAYS_HIGH = 63  # PLogic cell 63 is typically VCC/HIGH

# Common Camera Properties
CAMERA_TRIGGER_MODE_PROP = "TriggerMode"


class HardwareInterface:
    """
    A class to interface with microscope hardware via pymmcore-plus.
    It uses a global CMMCorePlus instance.
    """

    # Presets for laser control via SetCardPreset property
    LASER_PRESETS: Dict[str, str] = {
        "L1_ON": "5 - BNC5 enabled",
        "L2_ON": "6 - BNC6 enabled",
        "L3_ON": "7 - BNC7 enabled",
        "L4_ON": "8 - BNC8 enabled",
        "ALL_ON": "30 - BNC5-BNC8 enabled",
        "ALL_OFF": "9 - BNC5-8 all disabled",
    }
    # For interpreting PLogicOutputState if it's used/readable AND PLogicMode is manual TTL
    _BITMASK_LASER_STATES: Dict[str, int] = {
        "OFF": 0,
        "L1": 1,
        "L2": 2,
        "L3": 4,
        "L4": 8,  # L1 = bit 0 (BNC1), L2 = bit 1 (BNC2), etc.
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
        self.config_path: Optional[str] = config_path
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
                script_dir = os.path.dirname(__file__)
                path_from_script_dir_grandparent = os.path.join(
                    script_dir, "..", "..", target_config_to_load
                )
                path_from_cwd = os.path.join(os.getcwd(), target_config_to_load)
                if os.path.exists(target_config_to_load):
                    target_config_to_load = os.path.abspath(target_config_to_load)
                    print(
                        f"Using provided config path directly: {target_config_to_load}"
                    )
                elif os.path.exists(path_from_script_dir_grandparent):
                    target_config_to_load = os.path.abspath(
                        path_from_script_dir_grandparent
                    )
                    print(
                        f"Resolved relative config path (project root) to: {target_config_to_load}"
                    )
                elif os.path.exists(path_from_cwd):
                    target_config_to_load = os.path.abspath(path_from_cwd)
                    print(
                        f"Resolved relative config path (CWD) to: {target_config_to_load}"
                    )
                else:
                    print(
                        f"Warning: Config path '{self.config_path}' not found at common locations. Trying as is or expecting absolute path."
                    )
            if current_loaded_config == target_config_to_load and (
                "TigerCommHub" in mmc.getLoadedDevices()
            ):
                print(
                    f"Target configuration '{target_config_to_load}' is already loaded and seems valid."
                )
            else:
                print(
                    f"Current config is '{current_loaded_config}'. Attempting to load target: '{target_config_to_load}'"
                )
                try:
                    mmc.loadSystemConfiguration(target_config_to_load)
                    if mmc.systemConfigurationFile() == target_config_to_load and (
                        "TigerCommHub" in mmc.getLoadedDevices()
                    ):
                        print(
                            f"Successfully loaded configuration: {target_config_to_load}"
                        )
                        self.config_path = target_config_to_load
                    else:
                        raise RuntimeError(
                            f"Failed to verify load of {target_config_to_load}. Current: {mmc.systemConfigurationFile()}"
                        )
                except Exception as e:
                    print(
                        f"CRITICAL Error loading specified configuration '{target_config_to_load}': {e}"
                    )
                    traceback.print_exc()
                    raise
        else:
            if current_loaded_config and ("TigerCommHub" in mmc.getLoadedDevices()):
                print(
                    f"No specific config path provided to HardwareInterface. Using existing MMCore config: {current_loaded_config}"
                )
                self.config_path = current_loaded_config
            else:
                msg = "HardwareInterface initialized without a config_path, and MMCore has no valid configuration (or key device 'TigerCommHub' missing)."
                print(f"ERROR: {msg}")
                raise FileNotFoundError(msg)
        if not mmc.getLoadedDevices():
            print("WARNING: No devices seem to be loaded after initialization attempt!")
        else:
            print(
                f"HardwareInterface initialized. Effective config: {mmc.systemConfigurationFile()}"
            )
            # Set global shutter (BNC3) HIGH on startup using the new method
            print(
                "Attempting to set global shutter (PLogic BNC3) HIGH via EditCellConfig..."
            )
            if not self._set_bnc_line_state(
                bnc_line_number=3, high=True, save_settings=True
            ):
                print(
                    "Warning: Failed to set and save global shutter (PLogic BNC3) HIGH on startup."
                )
            else:
                print("Global shutter (PLogic BNC3) set HIGH.")

            print(f"Loaded devices: {mmc.getLoadedDevices()}")

    def _set_default_stages(self):
        if self.xy_stage in mmc.getLoadedDevices():
            try:
                mmc.setXYStageDevice(self.xy_stage)
                print(f"Default XY stage set to: {self.xy_stage}")
            except Exception as e:
                print(f"Warning: Could not set default XY stage '{self.xy_stage}': {e}")
        else:
            print(f"Warning: XY Stage device '{self.xy_stage}' not found.")
        if self.main_z_objective in mmc.getLoadedDevices():
            try:
                mmc.setFocusDevice(self.main_z_objective)
                print(f"Default Focus stage set to: {self.main_z_objective}")
            except Exception as e:
                print(
                    f"Warning: Could not set default Focus stage '{self.main_z_objective}': {e}"
                )
        else:
            print(f"Warning: Main Z objective '{self.main_z_objective}' not found.")

    @property
    def xy_stage(self) -> str:
        return "XYStage:XY:31"

    @property
    def main_z_objective(self) -> str:
        return "ZStage:Z:32"

    @property
    def galvo_scanner(self) -> str:
        return "Scanner:AB:33"

    @property
    def light_sheet_tilt(self) -> str:
        return "ZStage:F:35"

    @property
    def crisp_o1_focus_stage(self) -> str:
        return "ZStage:Z:32"

    @property
    def crisp_o1_autofocus_device(self) -> str:
        return "CRISPAFocus:Z:32"

    @property
    def crisp_o3_piezo_stage(self) -> str:
        return "PiezoStage:P:34"

    @property
    def crisp_o3_autofocus_device(self) -> str:
        return "CRISPAFocus:P:34"

    @property
    def plogic_lasers(self) -> str:
        return "PLogic:E:36"

    @property
    def camera1(self) -> str:
        return "Camera-1"

    @property
    def camera2(self) -> str:
        return "Camera-2"

    @property
    def multi_camera(self) -> str:
        return "Multi Camera"

    # --- Stage Control Methods ---
    # ... (All stage move/get methods remain the same) ...
    def move_xy(self, x: float, y: float, wait: bool = True):
        if mmc.getXYStageDevice() != self.xy_stage:
            if self.xy_stage in mmc.getLoadedDevices():
                mmc.setXYStageDevice(self.xy_stage)
            else:
                print(f"Error: XY Stage '{self.xy_stage}' not found.")
                return
        try:
            mmc.setXYPosition(x, y)
            print(f"Moved XY to ({x:.2f}, {y:.2f})")
        except Exception as e:
            print(f"Error moving XY: {e}")
            traceback.print_exc()

    def get_xy_position(self) -> Optional[Dict[str, float]]:
        if mmc.getXYStageDevice() != self.xy_stage:
            if self.xy_stage in mmc.getLoadedDevices():
                mmc.setXYStageDevice(self.xy_stage)
            else:
                print(f"Error: XY Stage '{self.xy_stage}' not found.")
                return None
        try:
            return {"x": mmc.getXPosition(), "y": mmc.getYPosition()}
        except Exception as e:
            print(f"Error getting XY pos: {e}")
            traceback.print_exc()
            return None

    def move_z_objective(self, z_um: float, wait: bool = True):
        if self.main_z_objective not in mmc.getLoadedDevices():
            print(f"Error: Z Obj '{self.main_z_objective}' not found.")
            return
        try:
            mmc.setPosition(self.main_z_objective, z_um)
            print(f"Moved Z Obj to {z_um:.2f} µm")
        except Exception as e:
            print(f"Error moving Z Obj: {e}")
            traceback.print_exc()

    def get_z_objective_position(self) -> Optional[float]:
        if self.main_z_objective not in mmc.getLoadedDevices():
            print(f"Error: Z Obj '{self.main_z_objective}' not found.")
            return None
        try:
            return mmc.getPosition(self.main_z_objective)
        except Exception as e:
            print(f"Error getting Z Obj pos: {e}")
            traceback.print_exc()
            return None

    def set_p_objective_position(self, position_um: float, wait: bool = True):
        if self.crisp_o3_piezo_stage not in mmc.getLoadedDevices():
            print(f"Error: P Obj Piezo '{self.crisp_o3_piezo_stage}' not found.")
            return
        try:
            mmc.setPosition(self.crisp_o3_piezo_stage, position_um)
            print(f"Moved P Obj Piezo to {position_um:.3f} µm")
        except Exception as e:
            print(f"Error moving P Obj Piezo: {e}")
            traceback.print_exc()

    def get_p_objective_position(self) -> Optional[float]:
        if self.crisp_o3_piezo_stage not in mmc.getLoadedDevices():
            print(f"Error: P Obj Piezo '{self.crisp_o3_piezo_stage}' not found.")
            return None
        try:
            return mmc.getPosition(self.crisp_o3_piezo_stage)
        except Exception as e:
            print(f"Error getting P Obj Piezo pos: {e}")
            traceback.print_exc()
            return None

    def _get_galvo_property(self, property_name: str) -> Optional[float]:
        if self.galvo_scanner not in mmc.getLoadedDevices():
            print(f"Error: Galvo '{self.galvo_scanner}' not found.")
            return None
        try:
            if mmc.getDeviceType(self.galvo_scanner) != DeviceType.GalvoDevice:
                print(f"Warning: Galvo '{self.galvo_scanner}' not GalvoDevice.")
                return None
            if not mmc.hasProperty(self.galvo_scanner, property_name):
                print(f"Error: Galvo missing prop '{property_name}'.")
                return None
            return float(mmc.getProperty(self.galvo_scanner, property_name))
        except Exception as e:
            print(f"Error getting galvo prop '{property_name}': {e}")
            traceback.print_exc()
            return None

    def _set_galvo_property(self, property_name: str, value: float):
        if self.galvo_scanner not in mmc.getLoadedDevices():
            print(f"Error: Galvo '{self.galvo_scanner}' not found.")
            return
        try:
            if mmc.getDeviceType(self.galvo_scanner) != DeviceType.GalvoDevice:
                print(f"Warning: Galvo '{self.galvo_scanner}' not GalvoDevice.")
                return
            if not mmc.hasProperty(self.galvo_scanner, property_name):
                print(f"Error: Galvo missing prop '{property_name}'.")
                return
            mmc.setProperty(self.galvo_scanner, property_name, float(value))
            print(f"Set Galvo prop '{property_name}' to {value:.4f}")
        except Exception as e:
            print(f"Error setting galvo prop '{property_name}': {e}")
            traceback.print_exc()

    def get_galvo_x_offset_degrees(self) -> Optional[float]:
        return self._get_galvo_property("SingleAxisXOffset(deg)")

    def get_galvo_y_offset_degrees(self) -> Optional[float]:
        return self._get_galvo_property("SingleAxisYOffset(deg)")

    def set_galvo_x_offset_degrees(self, degrees: float):
        self._set_galvo_property("SingleAxisXOffset(deg)", degrees)

    def set_galvo_y_offset_degrees(self, degrees: float):
        self._set_galvo_property("SingleAxisYOffset(deg)", degrees)

    def move_light_sheet_tilt(self, tilt_um: float, wait: bool = True):
        if self.light_sheet_tilt not in mmc.getLoadedDevices():
            print(f"Error: Tilt stage '{self.light_sheet_tilt}' not found.")
            return
        try:
            mmc.setPosition(self.light_sheet_tilt, tilt_um)
            print(f"Moved Tilt to {tilt_um:.2f} µm")
        except Exception as e:
            print(f"Error moving Tilt: {e}")
            traceback.print_exc()

    def get_light_sheet_tilt(self) -> Optional[float]:
        if self.light_sheet_tilt not in mmc.getLoadedDevices():
            print(f"Error: Tilt stage '{self.light_sheet_tilt}' not found.")
            return None
        try:
            return mmc.getPosition(self.light_sheet_tilt)
        except Exception as e:
            print(f"Error getting Tilt pos: {e}")
            traceback.print_exc()
            return None

    def move_crisp_o1_target_focus(self, z_um: float, wait: bool = True):
        if self.crisp_o1_focus_stage not in mmc.getLoadedDevices():
            print(f"Error: CRISP O1 Stage '{self.crisp_o1_focus_stage}' not found.")
            return
        try:
            mmc.setPosition(self.crisp_o1_focus_stage, z_um)
            print(
                f"Moved CRISP O1 target focus (stage {self.crisp_o1_focus_stage}) to {z_um:.2f} µm"
            )
        except Exception as e:
            print(f"Error moving CRISP O1 target: {e}")
            traceback.print_exc()

    def move_crisp_o3_target_focus(self, piezo_um: float, wait: bool = True):
        print(
            f"Note: move_crisp_o3_target_focus calls set_p_objective_position for stage '{self.crisp_o3_piezo_stage}'."
        )
        self.set_p_objective_position(piezo_um, wait)

    def get_target_focus_positions(self) -> Dict[str, Optional[float]]:
        return {
            "O1_target_focus_um": self.get_position_safe(self.crisp_o1_focus_stage),
            "O3_target_focus_um": self.get_p_objective_position(),
        }

    def get_position_safe(self, device_label: str) -> Optional[float]:
        if device_label in mmc.getLoadedDevices():
            try:
                return mmc.getPosition(device_label)
            except Exception:
                return None
        return None

    def set_crisp_state(self, crisp_autofocus_device_label: str, state: str) -> bool:
        if crisp_autofocus_device_label not in mmc.getLoadedDevices():
            print(f"Error: CRISP dev '{crisp_autofocus_device_label}' not found.")
            return False
        try:
            allowed_states = mmc.getAllowedPropertyValues(
                crisp_autofocus_device_label, "CRISP State"
            )
            if state not in allowed_states:
                print(
                    f"Error: '{state}' not allowed for {crisp_autofocus_device_label}. Allowed: {allowed_states}"
                )
                return False
            mmc.setProperty(crisp_autofocus_device_label, "CRISP State", state)
            print(f"Set {crisp_autofocus_device_label} 'CRISP State' to '{state}'")
            if state.lower() in [
                "lock",
                "focus",
                "find rng",
                "logcal",
                "gaincal",
                "dcal",
                "ready",
            ]:
                time.sleep(0.5)
            return True
        except Exception as e:
            print(f"Error setting CRISP state for {crisp_autofocus_device_label}: {e}")
            traceback.print_exc()
            return False

    def get_crisp_state(self, crisp_autofocus_device_label: str) -> Optional[str]:
        if crisp_autofocus_device_label not in mmc.getLoadedDevices():
            print(f"Error: CRISP dev '{crisp_autofocus_device_label}' not found.")
            return None
        try:
            return mmc.getProperty(crisp_autofocus_device_label, "CRISP State")
        except Exception as e:
            print(f"Error getting CRISP state for {crisp_autofocus_device_label}: {e}")
            traceback.print_exc()
            return None

    # --- Laser Control & PLogic ---
    def get_plogic_mode(self) -> Optional[str]:
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
            time.sleep(0.1)
            return True
        except RuntimeError as e_rt:  # Catch specific pre-init error
            if "Cannot set pre-init property after initialization" in str(e_rt):
                print(
                    f"Info: PLogicMode ('{mode}') is a pre-init property and cannot be changed after system load. Current mode: {self.get_plogic_mode()}"
                )
                return False
            else:
                raise e_rt  # Re-raise other runtime errors
        except Exception as e:
            print(f"Error setting PLogicMode to '{mode}': {e}")
            traceback.print_exc()
            return False

    def set_laser_preset(
        self, preset_name_or_value: Union[str, int]
    ) -> bool:  # Using presets
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return False
        preset_string_to_set: Optional[str] = None
        descriptive_name = str(preset_name_or_value)
        if isinstance(preset_name_or_value, str):
            if preset_name_or_value.upper() in self.LASER_PRESETS:
                preset_string_to_set = self.LASER_PRESETS[preset_name_or_value.upper()]
                descriptive_name = (
                    f"{preset_name_or_value.upper()} ('{preset_string_to_set}')"
                )
            else:
                preset_string_to_set = preset_name_or_value
                descriptive_name = f"'{preset_string_to_set}' (direct string)"
        elif isinstance(preset_name_or_value, int):
            try:
                allowed_presets = mmc.getAllowedPropertyValues(
                    self.plogic_lasers, PLOGIC_SET_PRESET_PROP
                )
                for ap in allowed_presets:
                    if ap.startswith(str(preset_name_or_value) + " -"):
                        preset_string_to_set = ap
                        break
                if preset_string_to_set:
                    descriptive_name = (
                        f"PRESET_NUM_{preset_name_or_value} ('{preset_string_to_set}')"
                    )
                else:
                    print(
                        f"Error: Preset num {preset_name_or_value} does not match start of any allowed preset strings: {allowed_presets}"
                    )
                    return False
            except Exception as e:
                print(
                    f"Error finding string for preset num {preset_name_or_value}: {e}"
                )
                return False
        else:
            print(
                f"Error: Invalid type for laser preset: {type(preset_name_or_value)}."
            )
            return False
        if preset_string_to_set is None:
            print(
                f"Error: Could not determine preset string for: {preset_name_or_value}"
            )
            return False
        try:
            mmc.setProperty(
                self.plogic_lasers, PLOGIC_SET_PRESET_PROP, preset_string_to_set
            )
            print(f"Set PLogic ({self.plogic_lasers}) to preset: {descriptive_name}")
            time.sleep(0.1)
            return True
        except Exception as e:
            print(
                f"Error setting PLogic prop '{PLOGIC_SET_PRESET_PROP}' to '{preset_string_to_set}': {e}"
            )
            traceback.print_exc()
            return False

    def set_plogic_output_state(self, bitmask_name_or_value: Union[str, int]) -> bool:
        """Sets the PLogicOutputState directly using a bitmask.
        Ensure PLogicMode is set to a manual TTL control mode first that uses this property."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return False
        value_to_set: Optional[int] = None
        state_name_for_print = ""
        if isinstance(bitmask_name_or_value, str):
            state_name_upper = bitmask_name_or_value.upper()
            if state_name_upper in self._BITMASK_LASER_STATES:
                value_to_set = self._BITMASK_LASER_STATES[state_name_upper]
                state_name_for_print = state_name_upper
            else:
                print(
                    f"Error: Unknown bitmask name '{bitmask_name_or_value}'. Allowed: {list(self._BITMASK_LASER_STATES.keys())}"
                )
                return False
        elif isinstance(bitmask_name_or_value, int):
            if (
                0 <= bitmask_name_or_value <= 255
            ):  # PLogic can have up to 8 lines (0-255)
                value_to_set = bitmask_name_or_value  # Corrected assignment
                state_name_for_print = self._INT_TO_BITMASK_LASER_STATE_NAME.get(
                    value_to_set, f"INT_VAL_{value_to_set}"
                )
            else:
                print(
                    f"Error: Int value {bitmask_name_or_value} out of typical PLogicOutputState range (0-255)."
                )
                return False
        else:
            print(
                f"Error: Invalid type for PLogicOutputState: {type(bitmask_name_or_value)}."
            )
            return False
        try:
            mmc.setProperty(
                self.plogic_lasers, PLOGIC_OUTPUT_STATE_PROP, int(value_to_set)
            )
            print(
                f"Set PLogic ({self.plogic_lasers}.{PLOGIC_OUTPUT_STATE_PROP}) to '{state_name_for_print}' (Value: {value_to_set})"
            )
            return True
        except Exception as e:
            print(f"Error setting PLogic prop '{PLOGIC_OUTPUT_STATE_PROP}': {e}")
            traceback.print_exc()
            return False

    def get_plogic_output_state_value(
        self,
    ) -> Optional[int]:  # Renamed from get_laser_output_state for clarity
        """Reads PLogicOutputState and attempts to return as an integer.
        Returns None if not readable or not an integer."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: PLogic dev '{self.plogic_lasers}' not found.")
            return None
        try:
            val_str = mmc.getProperty(self.plogic_lasers, PLOGIC_OUTPUT_STATE_PROP)
            return int(val_str)
        except ValueError:
            print(
                f"Warning: PLogic property '{PLOGIC_OUTPUT_STATE_PROP}' on '{self.plogic_lasers}' returned non-integer: '{val_str}' (Mode: {self.get_plogic_mode()})"  # type: ignore
            )
            return None
        except Exception as e:
            print(f"Error getting PLogic prop '{PLOGIC_OUTPUT_STATE_PROP}': {e}")
            return None

    def _set_bnc_line_state(
        self, bnc_line_number: int, high: bool, save_settings: bool = False
    ) -> bool:
        """
        Sets a specific PLogic BNC line HIGH or LOW using the EditCellConfig method.
        This configures the BNC output cell to mirror an "always HIGH" (cell 63)
        or "always LOW" (cell 0) PLogic internal cell.

        BNC lines are 1-indexed.

        Args:
            bnc_line_number: The 1-indexed BNC line (1-8).
            high: True to set the BNC line HIGH, False to set it LOW.
            save_settings: If True, attempts to save the setting to the PLogic card.

        Returns:
            True if successful, False otherwise.
        """
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(
                f"Error: PLogic device '{self.plogic_lasers}' not found for BNC control."
            )
            return False

        if not (
            1 <= bnc_line_number <= 8
        ):  # PLogic typically has 8 TTL outputs (BNC1-8)
            print(f"Error: bnc_line_number {bnc_line_number} is out of range (1-8).")
            return False

        # PLogic BNC output cells are typically addressed starting from 33 for BNC1
        # BNC1 -> 33, BNC2 -> 34, ..., BNC8 -> 40
        plogic_output_cell_address = bnc_line_number + 32

        target_source_cell = (
            PLOGIC_CELL_ADDR_ALWAYS_HIGH if high else PLOGIC_CELL_ADDR_ALWAYS_LOW
        )

        action = "HIGH" if high else "LOW"
        print(
            f"PLogic: Setting BNC {bnc_line_number} (output cell {plogic_output_cell_address}) to {action} "
            f"by pointing to cell {target_source_cell}."
        )

        try:
            mmc.setProperty(
                self.plogic_lasers,
                PLOGIC_POINTER_POSITION_PROP,
                str(plogic_output_cell_address),
            )
            time.sleep(0.05)  # Short delay
            mmc.setProperty(
                self.plogic_lasers,
                PLOGIC_EDIT_CELL_CONFIG_PROP,
                str(target_source_cell),
            )
            time.sleep(0.05)  # Short delay

            if save_settings:
                print(
                    f"  Saving PLogic settings to card ({PLOGIC_VAL_SAVE_SETTINGS})..."
                )
                mmc.setProperty(
                    self.plogic_lasers,
                    PLOGIC_SAVE_SETTINGS_PROP,
                    PLOGIC_VAL_SAVE_SETTINGS,
                )
                time.sleep(0.1)  # Saving might take a bit longer
            print(f"PLogic: BNC {bnc_line_number} successfully set to {action}.")
            return True
        except Exception as e:
            print(f"Error setting PLogic BNC {bnc_line_number} state: {e}")
            traceback.print_exc()
            return False

    # --- Camera Control ---
    def get_camera_trigger_mode(self, camera_label: str) -> Optional[str]:
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Cam dev '{camera_label}' not found.")
            return None
        try:
            if mmc.hasProperty(camera_label, CAMERA_TRIGGER_MODE_PROP):
                return mmc.getProperty(camera_label, CAMERA_TRIGGER_MODE_PROP)
            else:
                print(
                    f"Warning: Cam '{camera_label}' no prop '{CAMERA_TRIGGER_MODE_PROP}'."
                )
                return None
        except Exception as e:
            print(f"Error getting trigger mode for {camera_label}: {e}")
            traceback.print_exc()
            return None

    def set_camera_trigger_mode(self, camera_label: str, mode: str) -> bool:
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Cam dev '{camera_label}' not found.")
            return False
        try:
            if not mmc.hasProperty(camera_label, CAMERA_TRIGGER_MODE_PROP):
                print(
                    f"Error: Cam '{camera_label}' no prop '{CAMERA_TRIGGER_MODE_PROP}'."
                )
                return False
            allowed_modes = mmc.getAllowedPropertyValues(
                camera_label, CAMERA_TRIGGER_MODE_PROP
            )
            if mode not in allowed_modes:
                print(
                    f"Error: Mode '{mode}' not allowed for {camera_label}. Allowed: {allowed_modes}"
                )
                return False
            mmc.setProperty(camera_label, CAMERA_TRIGGER_MODE_PROP, mode)
            print(f"Set {camera_label} trigger mode to '{mode}'.")
            return True
        except Exception as e:
            print(f"Error setting trigger mode for {camera_label} to '{mode}': {e}")
            traceback.print_exc()
            return False

    def snap_image(
        self, camera_label: Optional[str] = None, exposure_ms: Optional[float] = None
    ) -> Optional[Any]:  # numpy.ndarray
        original_camera = None
        original_exposure = None
        active_camera_label = ""
        final_image_data = None
        try:
            if camera_label:
                if camera_label not in mmc.getLoadedDevices():
                    print(f"Error: Cam '{camera_label}' not found.")
                    return None
                active_camera_label = camera_label
                original_camera = mmc.getCameraDevice()
                if original_camera != active_camera_label:
                    mmc.setCameraDevice(active_camera_label)
            else:
                active_camera_label = mmc.getCameraDevice()
                if not active_camera_label:
                    print("Error: No camera selected.")
                    return None
            print(f"Snapping with camera: {active_camera_label}")
            if exposure_ms is not None:
                original_exposure = mmc.getExposure()
                mmc.setExposure(exposure_ms)
                print(
                    f"Set exposure for {active_camera_label} to {mmc.getExposure()} ms."
                )
            mmc.snapImage()
            print(f"Snap command completed for {active_camera_label}.")
            if active_camera_label == self.multi_camera:
                print("Multi Cam: getting images from channel 0 and 1.")
                try:
                    img1 = mmc.getImage(0)
                    print(
                        f"  Ch0 shape: {img1.shape if img1 is not None else 'None'}, dtype: {img1.dtype if img1 is not None else 'None'}"
                    )
                    img2 = mmc.getImage(1)
                    print(
                        f"  Ch1 shape: {img2.shape if img2 is not None else 'None'}, dtype: {img2.dtype if img2 is not None else 'None'}"
                    )
                    if img1 is not None and img2 is not None:
                        final_image_data = np.stack([img1, img2])
                        print(f"  Stacked. Final shape: {final_image_data.shape}")
                    elif img1 is not None:
                        print("  Warn: Got Ch0 not Ch1.")
                        final_image_data = img1
                    else:
                        print("  Error: Failed to get Ch images.")
                        final_image_data = None
                except Exception as e_mc_ch:
                    print(f"  Error getting multi-ch images: {e_mc_ch}")
                    final_image_data = None
                    if final_image_data is None:
                        print(
                            f"  Fallback to generic getImage() for {self.multi_camera}"
                        )
                        final_image_data = mmc.getImage()
            else:
                final_image_data = mmc.getImage()
            if final_image_data is not None:
                print(
                    f"Image obtained. Shape: {final_image_data.shape}, dtype: {final_image_data.dtype}"
                )
            else:
                print(f"Failed to obtain image data from {active_camera_label}.")
            return final_image_data
        except RuntimeError as e_rt:
            print(f"!!! RuntimeError snapping with {active_camera_label}: {e_rt} !!!")
            return None
        except Exception as e:
            print(f"Error during snap_image for {active_camera_label}: {e}")
            traceback.print_exc()
            return None
        finally:
            if (
                exposure_ms is not None
                and original_exposure is not None
                and active_camera_label
            ):
                try:
                    if mmc.getCameraDevice() == active_camera_label:
                        if mmc.getExposure() != original_exposure:
                            mmc.setExposure(original_exposure)
                            print(
                                f"Restored exposure for {active_camera_label} to {original_exposure} ms."
                            )
                except Exception as e_restore_exp:
                    print(
                        f"Warn: Could not restore exposure for {active_camera_label}: {e_restore_exp}"
                    )
            if (
                original_camera
                and original_camera != mmc.getCameraDevice()
                and active_camera_label
            ):
                try:
                    mmc.setCameraDevice(original_camera)
                    print(f"Restored active camera to {original_camera}.")
                except Exception as e_restore_cam:
                    print(
                        f"Warn: Could not restore original camera '{original_camera}': {e_restore_cam}"
                    )

    # --- System Shutdown ---
    def shutdown_hardware(self, reset_core: bool = True):
        print("Shutting down hardware interface...")

        # Set global shutter (BNC3) LOW on shutdown using the new method
        print(
            "Attempting to set global shutter (PLogic BNC3) LOW via EditCellConfig before shutdown..."
        )
        if self.plogic_lasers in mmc.getLoadedDevices():
            if not self._set_bnc_line_state(
                bnc_line_number=3, high=False, save_settings=True
            ):
                print(
                    "Warning: Failed to set and save global shutter (PLogic BNC3) LOW on shutdown."
                )
            else:
                print("Global shutter (PLogic BNC3) set LOW.")
        else:
            print(
                f"PLogic device '{self.plogic_lasers}' not loaded, cannot set BNC3 LOW during shutdown."
            )

        if reset_core:
            mmc.reset()
            print("MMCore reset.")
        else:
            mmc.unloadAllDevices()
            print("All devices unloaded.")
        print("Hardware shutdown complete.")


# --- Example Usage (can be in a separate script that imports this module) ---
if __name__ == "__main__":
    print("Running HardwareInterface diagnostic test...")
    cfg_path = "hardware_profiles/20250523-OPM.cfg"
    hw_interface = None
    original_plogic_mode = None

    try:
        hw_interface = HardwareInterface(config_path=cfg_path)

        print("\n--- Testing PLogic for Camera Trigger on BNC 1 (TTL Line 0) ---")

        original_plogic_mode = hw_interface.get_plogic_mode()
        if original_plogic_mode:
            print(f"Initial PLogicMode: {original_plogic_mode}")
            try:
                allowed_modes = mmc.getAllowedPropertyValues(
                    hw_interface.plogic_lasers, PLOGIC_MODE_PROP
                )
                print(
                    f"Allowed PLogicModes for {hw_interface.plogic_lasers}: {allowed_modes}"
                )
            except Exception as e_allowed_modes:
                print(f"Could not get allowed PLogicModes: {e_allowed_modes}")
        else:
            print(
                "Critical: Could not read initial PLogicMode. Cannot reliably test PLogic."
            )

        # Target mode for direct TTL control.
        # User identified 'Seven-channel TTL shutter' as a candidate.
        manual_ttl_mode_candidate = "Seven-channel TTL shutter"
        mode_set_for_trigger_test = False

        if original_plogic_mode != manual_ttl_mode_candidate:
            print(
                f"\nAttempting to set PLogicMode to '{manual_ttl_mode_candidate}' for trigger testing..."
            )
            # Note: set_plogic_mode will print an error and return False if mode is pre-init or not allowed.
            if hw_interface.set_plogic_mode(manual_ttl_mode_candidate):
                current_mode_check = hw_interface.get_plogic_mode()
                if current_mode_check == manual_ttl_mode_candidate:
                    print(
                        f"PLogicMode successfully set to '{manual_ttl_mode_candidate}'."
                    )
                    mode_set_for_trigger_test = True
                else:  # Should have been caught by set_plogic_mode if pre-init
                    print(
                        f"Warning: PLogicMode was commanded to '{manual_ttl_mode_candidate}', but readback is '{current_mode_check}'."
                    )
                    mode_set_for_trigger_test = (
                        True  # Proceed if set_plogic_mode didn't error
                    )
            # else: set_plogic_mode would have printed an error.
        else:
            print(f"\nPLogicMode is already '{manual_ttl_mode_candidate}'.")
            mode_set_for_trigger_test = True

        if mode_set_for_trigger_test:
            print(
                "\nGenerating a pulse on BNC 1 (TTL Line 0 using PLogicOutputState)..."
            )

            initial_output_state = hw_interface.get_plogic_output_state_value()
            print(
                f"PLogicOutputState before pulsing (in mode '{hw_interface.get_plogic_mode()}'): {initial_output_state}"
            )

            print("Setting PLogicOutputState to 0 (all lines LOW)...")
            if hw_interface.set_plogic_output_state(0):
                time.sleep(0.1)
                state_after_off = hw_interface.get_plogic_output_state_value()
                print(f"  PLogicOutputState after setting to 0: {state_after_off}")
            else:
                print("  Failed to set PLogicOutputState to 0.")

            print("Setting PLogicOutputState to 1 (BNC 1 HIGH)...")
            if hw_interface.set_plogic_output_state(1):  # Bitmask for line 0 (BNC1)
                print("  BNC 1 (TTL Line 0) should be HIGH now. Check oscilloscope.")
                time.sleep(0.5)

                print("Setting PLogicOutputState to 0 (BNC 1 LOW)...")
                if hw_interface.set_plogic_output_state(0):
                    print("  BNC 1 (TTL Line 0) should be LOW now.")
                    time.sleep(0.1)
                    state_after_pulse = hw_interface.get_plogic_output_state_value()
                    print(f"  PLogicOutputState after pulse: {state_after_pulse}")
                else:
                    print(
                        "  Failed to set PLogicOutputState back to 0 after pulse HIGH."
                    )
            else:
                print("  Failed to set PLogicOutputState to 1 (BNC 1 HIGH).")
        else:
            print(
                "PLogicMode not set to a manual TTL control mode. Skipping BNC 1 pulse test."
            )

        print("\n--- End of PLogic Camera Trigger Test ---")

    except FileNotFoundError as e:
        print(f"Initialization failed: {e}")
    except Exception as e:
        print(f"An error occurred during diagnostic test: {e}")
        traceback.print_exc()
    finally:
        if hw_interface:
            if original_plogic_mode:
                current_mode_at_end = hw_interface.get_plogic_mode()
                if current_mode_at_end and current_mode_at_end != original_plogic_mode:
                    print(
                        f"\nRestoring PLogicMode to original value: '{original_plogic_mode}'..."
                    )
                    if hw_interface.set_plogic_mode(original_plogic_mode):
                        print(
                            f"  PLogicMode restored. Current mode: {hw_interface.get_plogic_mode()}"
                        )
                    else:
                        print(
                            f"  Warning: Failed to restore PLogicMode to '{original_plogic_mode}'."
                        )
                elif current_mode_at_end:
                    print(
                        f"\nPLogicMode is '{current_mode_at_end}' (Original was: '{original_plogic_mode}')."
                    )

            print(
                "\nAttempting to set PLogicOutputState to 0 in finally block (all lines LOW)..."
            )
            if hw_interface.set_plogic_output_state(0):
                final_output_state = hw_interface.get_plogic_output_state_value()
                print(f"  Final PLogicOutputState: {final_output_state}")
            else:
                print(
                    "  Warning: Failed to set PLogicOutputState to 0 in finally block."
                )

            print("\nDiagnostic test finished. Hardware not automatically shut down.")
