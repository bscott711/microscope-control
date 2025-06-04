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
PLOGIC_MODE_PROP = "PLogicMode"


class HardwareInterface:
    """
    A class to interface with microscope hardware via pymmcore-plus.
    It uses a global CMMCorePlus instance.
    """

    # Presets for laser control via SetCardPreset property
    # Updated to use the full string labels as reported by getAllowedPropertyValues
    LASER_PRESETS: Dict[str, str] = {  # Values are now strings
        "L1_ON": "5 - BNC5 enabled",
        "L2_ON": "6 - BNC6 enabled",
        "L3_ON": "7 - BNC7 enabled",
        "L4_ON": "8 - BNC8 enabled",
        # Assuming preset 30 is for all 4 lasers on simultaneously.
        # The allowed values list shows '30 - BNC5-BNC8 enabled'.
        "ALL_ON": "30 - BNC5-BNC8 enabled",
        "ALL_OFF": "9 - BNC5-8 all disabled",
        # Note: Preset 50 ("7 channel laser: all lasers off") from previous documentation
        # might be different from preset 9 ("BNC5-8 all disabled").
        # We'll use preset 9 as it's clearly in your allowed values list for BNC5-8.
    }

    # For interpreting PLogicOutputState if it's used/readable AND PLogicMode is manual TTL
    # This might not be directly representative when using complex presets.
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

    def set_plogic_mode(self, mode: str) -> bool:  # Kept for completeness
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
        """Sets the PLogic card to a pre-defined preset using its string label or number."""
        if self.plogic_lasers not in mmc.getLoadedDevices():
            print(f"Error: Laser PLogic device '{self.plogic_lasers}' not found.")
            return False

        preset_value_to_set: Optional[str] = None  # Property expects string
        preset_description_for_print = ""

        if isinstance(preset_name_or_value, str):
            # If a key like "L1_ON" is given, look up its string value
            if preset_name_or_value.upper() in self.LASER_PRESETS:
                preset_value_to_set = self.LASER_PRESETS[preset_name_or_value.upper()]
                preset_description_for_print = (
                    f"{preset_name_or_value.upper()} ('{preset_value_to_set}')"
                )
            else:  # Assume it might be the direct string label of a preset
                preset_value_to_set = preset_name_or_value
                preset_description_for_print = f"'{preset_value_to_set}'"
        elif isinstance(preset_name_or_value, int):
            # If an int is given, assume it's a preset number and convert to string for setProperty
            # Also try to find its descriptive name for logging
            preset_value_to_set = str(preset_name_or_value)
            preset_description_for_print = f"PRESET_NUM_{preset_name_or_value}"
            for name, str_val in self.LASER_PRESETS.items():
                # This check is a bit weak if preset numbers are not unique in string labels
                if str_val.startswith(str(preset_name_or_value) + " -"):
                    preset_description_for_print = f"{name} ('{str_val}')"
                    break
        else:
            print(
                f"Error: Invalid type for laser preset: {type(preset_name_or_value)}. Must be str or int."
            )
            return False

        try:
            # Ensure the value being sent is a string, as per getAllowedPropertyValues output
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
                return {"value": -1, "name": "NON_INTEGER_STATE", "raw_string": val_str}
        except Exception as e:
            print(f"Error getting PLogic prop '{PLOGIC_OUTPUT_STATE_PROP}': {e}")
            return None

    # --- Camera Control ---
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
    cfg_path = "hardware_profiles/20250523-OPM.cfg"  # Path relative to project root
    hw_interface = None
    original_plogic_mode = None

    try:
        hw_interface = HardwareInterface(config_path=cfg_path)

        print("\n--- Testing Laser Control via Presets ---")

        original_plogic_mode = hw_interface.get_plogic_mode()
        if original_plogic_mode:
            print(f"Initial PLogicMode: {original_plogic_mode}")
            try:
                allowed_presets = mmc.getAllowedPropertyValues(
                    hw_interface.plogic_lasers, PLOGIC_SET_PRESET_PROP
                )
                print(
                    f"Allowed string values for '{PLOGIC_SET_PRESET_PROP}' on {hw_interface.plogic_lasers}: {allowed_presets}"
                )
            except Exception as e_allowed:
                print(
                    f"Could not get allowed values for '{PLOGIC_SET_PRESET_PROP}': {e_allowed}"
                )
        else:
            print(
                "Could not read initial PLogicMode. Presets might rely on a specific mode (e.g., 'diSPIM Shutter' from your config)."
            )

        test_presets_to_use = {
            "Laser 1 ON": "L1_ON",  # Will map to "5 - BNC5 enabled"
            "Laser 2 ON": "L2_ON",  # Will map to "6 - BNC6 enabled"
            "Laser 3 ON": "L3_ON",  # Will map to "7 - BNC7 enabled"
            "Laser 4 ON": "L4_ON",  # Will map to "8 - BNC8 enabled"
            "All 4 Lasers ON": "ALL_ON",  # Will map to "30 - BNC5-BNC8 enabled"
            "All Lasers OFF": "ALL_OFF",  # Will map to "9 - BNC5-8 all disabled"
        }

        for descriptive_name, preset_key in test_presets_to_use.items():
            # The preset_key ("L1_ON", etc.) will be used to look up the full string value
            # from hw_interface.LASER_PRESETS in the set_laser_preset method.
            print(
                f"\nAttempting to set: {descriptive_name} (using preset key: {preset_key})"
            )

            if hw_interface.set_laser_preset(preset_key):  # Pass the key like "L1_ON"
                time.sleep(0.5)
                output_state = hw_interface.get_laser_output_state()
                if output_state:
                    print(
                        f"  PLogicOutputState after preset '{preset_key}': Value={output_state.get('value')}, Raw='{output_state.get('raw_string')}' (Mode: {hw_interface.get_plogic_mode()})"
                    )
                else:
                    print(
                        f"  Could not read PLogicOutputState after setting preset {preset_key}."
                    )
            else:
                print(f"  Failed to set laser preset using key {preset_key}.")

            if preset_key != "ALL_OFF":
                print(f"  Setting lasers to ALL_OFF after testing {preset_key}...")
                hw_interface.set_laser_preset("ALL_OFF")
                time.sleep(0.2)

        print("\n--- End of Laser Preset Control Tests ---")

    except FileNotFoundError as e:
        print(f"Initialization failed: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
        traceback.print_exc()
    finally:
        if hw_interface:
            if original_plogic_mode:
                print(
                    f"\nPLogicMode at end of test: '{hw_interface.get_plogic_mode()}' (Original was: '{original_plogic_mode}')"
                )

            print(
                "\nEnsuring all lasers are OFF in finally block (using ALL_OFF preset)..."
            )
            if not hw_interface.set_laser_preset("ALL_OFF"):
                print("  Warning: Failed to set ALL_OFF preset in finally block.")
            else:
                final_output_state = hw_interface.get_laser_output_state()
                if final_output_state:
                    print(
                        f"  Final PLogicOutputState: Value={final_output_state.get('value')}, Raw='{final_output_state.get('raw_string')}'"
                    )
                else:
                    print(
                        "  Could not read final PLogicOutputState after attempting to set ALL_OFF preset."
                    )
            print("\nDiagnostic test finished. Hardware not automatically shut down.")
