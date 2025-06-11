import os  # For path joining if needed
import time  # Added for time.sleep in set_crisp_state and movement tests
import traceback
from typing import Any, Dict, Optional, Union

import numpy as np  # Added for stacking multi-camera images
from pymmcore_plus import CMMCorePlus, DeviceType  # Import DeviceType directly

# Initialize global core instance
mmc = CMMCorePlus.instance()

# Property names for PLogic card
PLOGIC_SET_PRESET_PROP = "SetCardPreset"
PLOGIC_OUTPUT_STATE_PROP = "PLogicOutputState"
PLOGIC_MODE_PROP = "PLogicMode"

# Common Camera Properties
CAMERA_TRIGGER_MODE_PROP = "TriggerMode"  # As identified from user's output


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

    # --- Laser Control ---
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
                    f"Error: Mode '{mode}' not allowed for PLogic. Allowed: {allowed_modes}"
                )
                return False
            mmc.setProperty(self.plogic_lasers, PLOGIC_MODE_PROP, mode)
            print(f"Set PLogicMode for {self.plogic_lasers} to '{mode}'")
            time.sleep(0.1)
            return True
        except Exception as e:
            print(f"Error setting PLogicMode to '{mode}': {e}")
            traceback.print_exc()
            return False

    def set_laser_preset(self, preset_name_or_value: Union[str, int]) -> bool:
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: Laser PLogic device '{self.plogic_lasers}' not found.")
            return False
        preset_value_to_set: Optional[str] = None
        preset_description_for_print = ""
        if isinstance(preset_name_or_value, str):
            preset_name_upper = preset_name_or_value.upper()
            if preset_name_upper in self.LASER_PRESETS:
                preset_value_to_set = self.LASER_PRESETS[preset_name_upper]
                preset_description_for_print = (
                    f"{preset_name_upper} ('{preset_value_to_set}')"
                )
            else:
                preset_value_to_set = preset_name_or_value
                preset_description_for_print = (
                    f"'{preset_value_to_set}' (direct string)"
                )
                print(
                    f"Warning: Preset name '{preset_name_or_value}' not in defined LASER_PRESETS dict. Attempting to use as direct string label."
                )
        elif isinstance(preset_name_or_value, int):
            preset_value_to_set = str(preset_name_or_value)
            preset_description_for_print = (
                f"PRESET_NUM_AS_STRING_{preset_name_or_value}"
            )
            for name, str_val in self.LASER_PRESETS.items():
                if str_val.startswith(str(preset_name_or_value) + " -"):
                    preset_description_for_print = f"{name} ('{str_val}')"
                    preset_value_to_set = str_val
                    break
        else:
            print(
                f"Error: Invalid type for laser preset: {type(preset_name_or_value)}. Must be str or int."
            )
            return False
        try:
            mmc.setProperty(
                self.plogic_lasers, PLOGIC_SET_PRESET_PROP, str(preset_value_to_set)
            )
            print(
                f"Set PLogic ({self.plogic_lasers}) to preset: {preset_description_for_print}"
            )
            time.sleep(0.1)
            return True
        except Exception as e:
            print(
                f"Error setting PLogic '{self.plogic_lasers}' prop '{PLOGIC_SET_PRESET_PROP}' to '{preset_value_to_set}': {e}"
            )
            traceback.print_exc()
            return False

    def get_laser_output_state(self) -> Optional[Dict[str, Union[int, str]]]:
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
                return {"value": -1, "name": "NON_INTEGER_STATE", "raw_string": val_str}
        except Exception as e:
            print(f"Error getting PLogic prop '{PLOGIC_OUTPUT_STATE_PROP}': {e}")
            return None

    # --- Camera Control ---
    def get_camera_trigger_mode(self, camera_label: str) -> Optional[str]:
        """Gets the current trigger mode of the specified camera."""
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Camera device '{camera_label}' not found.")
            return None
        try:
            if mmc.hasProperty(camera_label, CAMERA_TRIGGER_MODE_PROP):
                return mmc.getProperty(camera_label, CAMERA_TRIGGER_MODE_PROP)
            else:
                print(
                    f"Warning: Camera '{camera_label}' does not have property '{CAMERA_TRIGGER_MODE_PROP}'."
                )
                return None
        except Exception as e:
            print(f"Error getting trigger mode for {camera_label}: {e}")
            traceback.print_exc()
            return None

    def set_camera_trigger_mode(self, camera_label: str, mode: str) -> bool:
        """Sets the trigger mode of the specified camera."""
        if camera_label not in mmc.getLoadedDevices():
            print(f"Error: Camera device '{camera_label}' not found.")
            return False
        try:
            if not mmc.hasProperty(camera_label, CAMERA_TRIGGER_MODE_PROP):
                print(
                    f"Error: Camera '{camera_label}' does not have property '{CAMERA_TRIGGER_MODE_PROP}'. Cannot set mode."
                )
                return False

            allowed_modes = mmc.getAllowedPropertyValues(
                camera_label, CAMERA_TRIGGER_MODE_PROP
            )
            if mode not in allowed_modes:
                print(
                    f"Error: Mode '{mode}' is not an allowed trigger mode for {camera_label}. Allowed: {allowed_modes}"
                )
                return False

            mmc.setProperty(camera_label, CAMERA_TRIGGER_MODE_PROP, mode)
            print(f"Set {camera_label} trigger mode to '{mode}'.")
            # Verification
            # current_mode = self.get_camera_trigger_mode(camera_label)
            # if current_mode == mode:
            #     print(f"  Verified: {camera_label} trigger mode is now '{current_mode}'.")
            # else:
            #     print(f"  Warning: Failed to verify trigger mode change for {camera_label}. Current: '{current_mode}'.")
            return True  # Assume success if setProperty didn't error, verification can be separate
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
    original_trigger_mode_cam1: Optional[str] = None
    original_trigger_mode_cam2: Optional[str] = None

    def query_and_print_trigger_modes_for_test(
        camera_label_to_check: str,
    ) -> Optional[str]:
        print(f"\n--- Querying Trigger Mode for {camera_label_to_check} ---")
        if camera_label_to_check not in mmc.getLoadedDevices():
            print(f"Device {camera_label_to_check} not found.")
            return None

        if hw_interface is None:
            print("Error: hw_interface is not initialized.")
            return None

        current_mode = hw_interface.get_camera_trigger_mode(camera_label_to_check)
        if current_mode is not None:
            print(
                f"  Current '{CAMERA_TRIGGER_MODE_PROP}' for {camera_label_to_check}: '{current_mode}'"
            )
            try:
                allowed_values = mmc.getAllowedPropertyValues(
                    camera_label_to_check, CAMERA_TRIGGER_MODE_PROP
                )
                print(f"    Allowed Values: {allowed_values}")
            except Exception as e_allowed:
                print(
                    f"    Could not get allowed values for '{CAMERA_TRIGGER_MODE_PROP}': {e_allowed}"
                )
        else:
            print(
                f"  Could not get current trigger mode for {camera_label_to_check} (or property '{CAMERA_TRIGGER_MODE_PROP}' not found)."
            )
        return current_mode

    try:
        hw_interface = HardwareInterface(config_path=cfg_path)

        print("\n--- Testing Camera Trigger Mode Changes ---")

        # Get and store original trigger modes
        original_trigger_mode_cam1 = query_and_print_trigger_modes_for_test(
            hw_interface.camera1
        )
        original_trigger_mode_cam2 = query_and_print_trigger_modes_for_test(
            hw_interface.camera2
        )

        target_trigger_mode = "Edge Trigger"  # A common external trigger mode

        # Test Camera 1
        if (
            original_trigger_mode_cam1
        ):  # Only proceed if we could read the original mode
            print(
                f"\nAttempting to set {hw_interface.camera1} trigger mode to '{target_trigger_mode}'..."
            )
            if hw_interface.set_camera_trigger_mode(
                hw_interface.camera1, target_trigger_mode
            ):
                time.sleep(0.1)  # Brief pause for mode to apply
                new_mode_cam1 = hw_interface.get_camera_trigger_mode(
                    hw_interface.camera1
                )
                print(
                    f"  {hw_interface.camera1} trigger mode after set: '{new_mode_cam1}'"
                )
                if new_mode_cam1 != target_trigger_mode:
                    print(
                        f"  Warning: {hw_interface.camera1} mode did not change as expected."
                    )
            else:
                print(
                    f"  Failed to set trigger mode for {hw_interface.camera1} to '{target_trigger_mode}'."
                )

        # Test Camera 2
        if original_trigger_mode_cam2:
            print(
                f"\nAttempting to set {hw_interface.camera2} trigger mode to '{target_trigger_mode}'..."
            )
            if hw_interface.set_camera_trigger_mode(
                hw_interface.camera2, target_trigger_mode
            ):
                time.sleep(0.1)
                new_mode_cam2 = hw_interface.get_camera_trigger_mode(
                    hw_interface.camera2
                )
                print(
                    f"  {hw_interface.camera2} trigger mode after set: '{new_mode_cam2}'"
                )
                if new_mode_cam2 != target_trigger_mode:
                    print(
                        f"  Warning: {hw_interface.camera2} mode did not change as expected."
                    )
            else:
                print(
                    f"  Failed to set trigger mode for {hw_interface.camera2} to '{target_trigger_mode}'."
                )

        print("\n--- End of Camera Trigger Mode Tests ---")

    except FileNotFoundError as e:
        print(f"Initialization failed: {e}")
    except Exception as e:
        print(f"An error occurred during diagnostic test: {e}")
        traceback.print_exc()
    finally:
        if hw_interface:
            print("\n--- Restoring Original Camera Trigger Modes (if changed) ---")
            if (
                original_trigger_mode_cam1
                and hw_interface.get_camera_trigger_mode(hw_interface.camera1)
                != original_trigger_mode_cam1
            ):
                print(
                    f"Restoring {hw_interface.camera1} trigger mode to '{original_trigger_mode_cam1}'..."
                )
                hw_interface.set_camera_trigger_mode(
                    hw_interface.camera1, original_trigger_mode_cam1
                )
                print(
                    f"  {hw_interface.camera1} trigger mode after restore: '{hw_interface.get_camera_trigger_mode(hw_interface.camera1)}'"
                )
            elif original_trigger_mode_cam1:
                print(
                    f"{hw_interface.camera1} trigger mode is already '{original_trigger_mode_cam1}'."
                )

            if (
                original_trigger_mode_cam2
                and hw_interface.get_camera_trigger_mode(hw_interface.camera2)
                != original_trigger_mode_cam2
            ):
                print(
                    f"Restoring {hw_interface.camera2} trigger mode to '{original_trigger_mode_cam2}'..."
                )
                hw_interface.set_camera_trigger_mode(
                    hw_interface.camera2, original_trigger_mode_cam2
                )
                print(
                    f"  {hw_interface.camera2} trigger mode after restore: '{hw_interface.get_camera_trigger_mode(hw_interface.camera2)}'"
                )
            elif original_trigger_mode_cam2:
                print(
                    f"{hw_interface.camera2} trigger mode is already '{original_trigger_mode_cam2}'."
                )

            print("\nDiagnostic test finished. Hardware not automatically shut down.")
