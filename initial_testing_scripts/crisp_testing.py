from pymmcore_plus import CMMCorePlus, DeviceType  # Import DeviceType directly
from typing import Optional, Dict, Any
import traceback
import time  # Added for time.sleep in set_crisp_state and movement tests
import os  # For path joining if needed

# Initialize global core instance
# This allows the HardwareInterface to use the same core instance
# that might be initialized by napari-micromanager or another part of the application.
mmc = CMMCorePlus.instance()


class HardwareInterface:
    """
    A class to interface with microscope hardware via pymmcore-plus.
    It uses a global CMMCorePlus instance.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initializes the hardware interface.

        Args:
            config_path: Optional path to a Micro-Manager configuration file.
                         If provided, this config will be loaded if no config or a
                         different config is already loaded in the global mmc instance.
                         If None, the interface will use the existing configuration
                         in the global mmc instance, or raise an error if none is loaded.
        """
        self.config_path: Optional[str] = config_path
        self._initialize_hardware()
        self._set_default_stages()

    def _initialize_hardware(self):
        """
        Ensures a Micro-Manager configuration is loaded.
        - If self.config_path is set, it attempts to load this configuration
          if it's not already the active one.
        - If self.config_path is None, it checks if any configuration is loaded.
        - Raises FileNotFoundError if no configuration can be confirmed.
        """
        print("Initializing HardwareInterface...")
        current_loaded_config = ""
        try:
            current_loaded_config = mmc.systemConfigurationFile()
        except Exception as e:
            print(f"Note: Could not get initial system configuration file: {e}")

        target_config_to_load = self.config_path

        if target_config_to_load:
            # Ensure the path is absolute for robust loading
            if not os.path.isabs(target_config_to_load):
                potential_path_from_src_parent = os.path.join(
                    os.path.dirname(__file__), "..", "..", target_config_to_load
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

            if current_loaded_config == target_config_to_load and (
                "TigerCommHub" in mmc.getLoadedDevices()
            ):  # Assuming TigerCommHub is key
                print(
                    f"Target configuration '{target_config_to_load}' is already loaded and seems valid."
                )
            else:
                print(
                    f"Current config is '{current_loaded_config}'. Attempting to load target: '{target_config_to_load}'"
                )
                try:
                    mmc.loadSystemConfiguration(target_config_to_load)
                    # Verify
                    if mmc.systemConfigurationFile() == target_config_to_load and (
                        "TigerCommHub" in mmc.getLoadedDevices()
                    ):
                        print(
                            f"Successfully loaded configuration: {target_config_to_load}"
                        )
                        self.config_path = (
                            target_config_to_load  # Ensure stored path is correct
                        )
                    else:
                        raise RuntimeError(
                            f"Failed to verify load of {target_config_to_load}. Current: {mmc.systemConfigurationFile()}"
                        )
                except Exception as e:
                    print(
                        f"CRITICAL Error loading specified configuration '{target_config_to_load}': {e}"
                    )
                    traceback.print_exc()
                    raise  # Re-raise the exception to indicate critical failure
        else:  # No specific config_path provided to __init__
            if current_loaded_config and ("TigerCommHub" in mmc.getLoadedDevices()):
                print(
                    f"No specific config path provided to HardwareInterface. Using existing MMCore config: {current_loaded_config}"
                )
                self.config_path = current_loaded_config  # Store the existing path
            else:
                msg = (
                    "HardwareInterface initialized without a config_path, and "
                    "MMCore has no valid configuration (or key device 'TigerCommHub' missing)."
                )
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
        """Sets default XY and Focus stages if they exist."""
        if self.xy_stage in mmc.getLoadedDevices():
            try:
                mmc.setXYStageDevice(self.xy_stage)
                print(f"Default XY stage set to: {self.xy_stage}")
            except Exception as e:
                print(f"Warning: Could not set default XY stage '{self.xy_stage}': {e}")
        else:
            print(
                f"Warning: XY Stage device '{self.xy_stage}' not found in loaded devices."
            )

        if self.main_z_objective in mmc.getLoadedDevices():
            try:
                mmc.setFocusDevice(self.main_z_objective)
                print(f"Default Focus stage set to: {self.main_z_objective}")
            except Exception as e:
                print(
                    f"Warning: Could not set default Focus stage '{self.main_z_objective}': {e}"
                )
        else:
            print(
                f"Warning: Main Z objective device '{self.main_z_objective}' not found, cannot set as default focus."
            )

    # --- Device Names (as properties for easy access and modification) ---
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
    def crisp_o3_piezo_stage(self) -> str:  # This is your P:34 device
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

    # --- Stage Position Control ---
    def move_xy(self, x: float, y: float, wait: bool = True):
        """Moves the default XY stage. Assumes self.xy_stage is set as default."""
        if mmc.getXYStageDevice() != self.xy_stage:
            print(
                f"Warning: Default XY stage is '{mmc.getXYStageDevice()}', not '{self.xy_stage}'. Attempting to set."
            )
            if self.xy_stage in mmc.getLoadedDevices():
                mmc.setXYStageDevice(self.xy_stage)
            else:
                print(
                    f"Error: XY Stage device '{self.xy_stage}' not found. Cannot move."
                )
                return
        try:
            mmc.setXYPosition(x, y)
            if wait:
                mmc.waitForDevice(self.xy_stage)
            print(f"Moved XY to ({x:.2f}, {y:.2f})")  # Added formatting
        except Exception as e:
            print(f"Error moving XY stage: {e}")
            traceback.print_exc()

    def get_xy_position(self) -> Optional[Dict[str, float]]:
        """Gets the position of the default XY stage."""
        if mmc.getXYStageDevice() != self.xy_stage:
            print(
                f"Warning: Default XY stage is '{mmc.getXYStageDevice()}', not '{self.xy_stage}'. Attempting to set."
            )
            if self.xy_stage in mmc.getLoadedDevices():
                mmc.setXYStageDevice(self.xy_stage)
            else:
                print(
                    f"Error: XY Stage device '{self.xy_stage}' not found. Cannot get position."
                )
                return None
        try:
            return {
                "x": mmc.getXPosition(),
                "y": mmc.getYPosition(),
            }
        except Exception as e:
            print(f"Error getting XY position: {e}")
            traceback.print_exc()
            return None

    def move_z_objective(self, z_um: float, wait: bool = True):
        if self.main_z_objective not in mmc.getLoadedDevices():
            print(f"Error: Main Z objective '{self.main_z_objective}' not found.")
            return
        try:
            mmc.setPosition(self.main_z_objective, z_um)
            if wait:
                mmc.waitForDevice(self.main_z_objective)
            print(f"Moved Main Z Objective to {z_um:.2f} µm")  # Added formatting
        except Exception as e:
            print(f"Error moving Main Z Objective: {e}")
            traceback.print_exc()

    def get_z_objective_position(self) -> Optional[float]:
        if self.main_z_objective not in mmc.getLoadedDevices():
            print(f"Error: Main Z objective '{self.main_z_objective}' not found.")
            return None
        try:
            return mmc.getPosition(self.main_z_objective)
        except Exception as e:
            print(f"Error getting Main Z Objective position: {e}")
            traceback.print_exc()
            return None

    def set_p_objective_position(self, position_um: float, wait: bool = True):
        """Sets the position of the P objective piezo stage (PiezoStage:P:34)."""
        if self.crisp_o3_piezo_stage not in mmc.getLoadedDevices():
            print(
                f"Error: P Objective Piezo Stage '{self.crisp_o3_piezo_stage}' not found."
            )
            return
        try:
            mmc.setPosition(self.crisp_o3_piezo_stage, position_um)
            if wait:
                mmc.waitForDevice(self.crisp_o3_piezo_stage)
            print(
                f"Moved P Objective Piezo to {position_um:.3f} µm"
            )  # Added formatting
        except Exception as e:
            print(f"Error moving P Objective Piezo: {e}")
            traceback.print_exc()

    def get_p_objective_position(self) -> Optional[float]:
        """Gets the position of the P objective piezo stage (PiezoStage:P:34)."""
        if self.crisp_o3_piezo_stage not in mmc.getLoadedDevices():
            print(
                f"Error: P Objective Piezo Stage '{self.crisp_o3_piezo_stage}' not found."
            )
            return None
        try:
            return mmc.getPosition(self.crisp_o3_piezo_stage)
        except Exception as e:
            print(f"Error getting P Objective Piezo position: {e}")
            traceback.print_exc()
            return None

    # --- Galvo Control ---
    def _get_galvo_property(self, property_name: str) -> Optional[float]:
        """Helper to get a galvo property, returns it as float if possible."""
        if self.galvo_scanner not in mmc.getLoadedDevices():
            print(f"Error: Galvo scanner '{self.galvo_scanner}' not found.")
            return None
        try:
            device_type_val = mmc.getDeviceType(self.galvo_scanner)
            if device_type_val != DeviceType.GalvoDevice:
                print(
                    f"Warning: Device '{self.galvo_scanner}' is type '{device_type_val}', not GalvoDevice. Cannot get property '{property_name}'."
                )
                return None

            if not mmc.hasProperty(self.galvo_scanner, property_name):
                print(
                    f"Error: Galvo scanner '{self.galvo_scanner}' does not have property '{property_name}'."
                )
                print(
                    f"  Available properties: {mmc.getDevicePropertyNames(self.galvo_scanner)}"
                )
                return None

            return float(mmc.getProperty(self.galvo_scanner, property_name))
        except Exception as e:
            print(f"Error getting galvo property '{property_name}': {e}")
            traceback.print_exc()
            return None

    def _set_galvo_property(self, property_name: str, value: float):
        """Helper to set a galvo property."""
        if self.galvo_scanner not in mmc.getLoadedDevices():
            print(f"Error: Galvo scanner '{self.galvo_scanner}' not found.")
            return
        try:
            device_type_val = mmc.getDeviceType(self.galvo_scanner)
            if device_type_val != DeviceType.GalvoDevice:
                print(
                    f"Warning: Device '{self.galvo_scanner}' is type '{device_type_val}', not GalvoDevice. Cannot set property '{property_name}'."
                )
                return

            if not mmc.hasProperty(self.galvo_scanner, property_name):
                print(
                    f"Error: Galvo scanner '{self.galvo_scanner}' does not have property '{property_name}'."
                )
                print(
                    f"  Available properties: {mmc.getDevicePropertyNames(self.galvo_scanner)}"
                )
                return

            mmc.setProperty(self.galvo_scanner, property_name, float(value))
            print(
                f"Set Galvo property '{property_name}' to {value:.4f}"
            )  # Added formatting
        except Exception as e:
            print(f"Error setting galvo property '{property_name}': {e}")
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
            print(f"Error: Light sheet tilt stage '{self.light_sheet_tilt}' not found.")
            return
        try:
            mmc.setPosition(self.light_sheet_tilt, tilt_um)
            if wait:
                mmc.waitForDevice(self.light_sheet_tilt)
            print(f"Moved Light Sheet Tilt to {tilt_um:.2f} µm")  # Added formatting
        except Exception as e:
            print(f"Error moving Light Sheet Tilt: {e}")
            traceback.print_exc()

    def get_light_sheet_tilt(self) -> Optional[float]:
        if self.light_sheet_tilt not in mmc.getLoadedDevices():
            print(f"Error: Light sheet tilt stage '{self.light_sheet_tilt}' not found.")
            return None
        try:
            return mmc.getPosition(self.light_sheet_tilt)
        except Exception as e:
            print(f"Error getting Light Sheet Tilt position: {e}")
            traceback.print_exc()
            return None

    # --- CRISP Focus Control ---
    def move_crisp_o1_target_focus(self, z_um: float, wait: bool = True):
        if self.crisp_o1_focus_stage not in mmc.getLoadedDevices():
            print(
                f"Error: CRISP O1 focus stage '{self.crisp_o1_focus_stage}' not found."
            )
            return
        try:
            mmc.setPosition(self.crisp_o1_focus_stage, z_um)
            if wait:
                mmc.waitForDevice(self.crisp_o1_focus_stage)
            print(
                f"Moved CRISP O1 target focus (stage {self.crisp_o1_focus_stage}) to {z_um:.2f} µm"
            )
        except Exception as e:
            print(f"Error moving CRISP O1 target focus: {e}")
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
        """
        Sets the state of a CRISP device (e.g., "Lock", "Idle", "Focus", "Find Rng", "Ready").
        Valid labels: self.crisp_o1_autofocus_device or self.crisp_o3_autofocus_device.
        """
        if crisp_autofocus_device_label not in mmc.getLoadedDevices():
            print(f"Error: CRISP device '{crisp_autofocus_device_label}' not found.")
            return False
        try:
            # The property name for CRISP state is "CRISP State"
            # Ensure the 'state' string is one of the allowed values for the device.
            allowed_states = mmc.getAllowedPropertyValues(
                crisp_autofocus_device_label, "CRISP State"
            )
            if state not in allowed_states:
                print(
                    f"Error: '{state}' is not an allowed state for {crisp_autofocus_device_label}. Allowed: {allowed_states}"
                )
                return False

            mmc.setProperty(crisp_autofocus_device_label, "CRISP State", state)
            print(f"Set {crisp_autofocus_device_label} 'CRISP State' to '{state}'")

            # Add a small delay if moving to an active state like "Focus", "Ready", or "Lock"
            # to allow the system to react or the LED to turn on.
            if state.lower() in [
                "lock",
                "focus",
                "find rng",
                "logcal",
                "gaincal",
                "dcal",
                "ready",
            ]:  # Added "ready"
                time.sleep(0.5)  # Adjust delay as needed
            return True
        except Exception as e:
            print(f"Error setting CRISP state for {crisp_autofocus_device_label}: {e}")
            traceback.print_exc()
            return False

    def get_crisp_state(self, crisp_autofocus_device_label: str) -> Optional[str]:
        """Gets the current state of a CRISP device."""
        if crisp_autofocus_device_label not in mmc.getLoadedDevices():
            print(f"Error: CRISP device '{crisp_autofocus_device_label}' not found.")
            return None
        try:
            return mmc.getProperty(crisp_autofocus_device_label, "CRISP State")
        except Exception as e:
            print(f"Error getting CRISP state for {crisp_autofocus_device_label}: {e}")
            traceback.print_exc()
            return None

    # --- Camera Control ---
    def snap_image(
        self, camera_label: Optional[str] = None, exposure_ms: Optional[float] = None
    ) -> Optional[Any]:  # numpy.ndarray
        original_camera = None
        original_exposure = None
        active_camera_label = ""

        try:
            if camera_label:
                if camera_label not in mmc.getLoadedDevices():
                    print(f"Error: Specified camera '{camera_label}' not found.")
                    return None
                active_camera_label = camera_label
                original_camera = mmc.getCameraDevice()
                if original_camera != active_camera_label:
                    mmc.setCameraDevice(active_camera_label)
            else:
                active_camera_label = mmc.getCameraDevice()
                if not active_camera_label:
                    print("Error: No camera device selected or specified.")
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
            img = mmc.getImage()
            print(
                f"Image obtained from {active_camera_label}. Shape: {img.shape if img is not None else 'None'}, dtype: {img.dtype if img is not None else 'None'}"
            )
            return img

        except RuntimeError as e_rt:
            print(f"!!! RuntimeError snapping with {active_camera_label}: {e_rt} !!!")
            print(
                "    Check Micro-Manager CoreLog. Ensure camera power/connection and MM GUI Live View is OFF."
            )
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
                        f"Warning: Could not restore exposure for {active_camera_label}: {e_restore_exp}"
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
                        f"Warning: Could not restore original camera '{original_camera}': {e_restore_cam}"
                    )

    # --- System Shutdown ---
    def shutdown_hardware(self, reset_core: bool = True):
        print("Shutting down hardware interface...")
        if reset_core:
            print("Resetting MMCore (unloads all devices and resets core state).")
            mmc.reset()
        else:
            print("Unloading all devices (core state might persist).")
            mmc.unloadAllDevices()
        print("Hardware shutdown complete.")


# --- Example Usage (can be in a separate script that imports this module) ---
if __name__ == "__main__":
    print("Running HardwareInterface diagnostic test...")
    cfg_path = "hardware_profiles/20250523-OPM.cfg"

    hw_interface = None
    # Define state trackers for finally block
    crisp1_state_changed_to_ready = False
    crisp3_state_changed_to_ready = False

    try:
        hw_interface = HardwareInterface(config_path=cfg_path)

        print("\n--- Initial Hardware States (before CRISP test) ---")
        crisp1_initial_state = hw_interface.get_crisp_state(
            hw_interface.crisp_o1_autofocus_device
        )
        print(
            f"CRISP O1 Initial State ({hw_interface.crisp_o1_autofocus_device}): {crisp1_initial_state if crisp1_initial_state is not None else 'N/A'}"
        )

        crisp3_initial_state = hw_interface.get_crisp_state(
            hw_interface.crisp_o3_autofocus_device
        )
        print(
            f"CRISP O3 Initial State ({hw_interface.crisp_o3_autofocus_device}): {crisp3_initial_state if crisp3_initial_state is not None else 'N/A'}"
        )

        target_crisp_state = "Ready"  # Target state for testing

        # --- Test CRISP O1 ---
        print(
            f"\n--- Testing CRISP State Changes ({hw_interface.crisp_o1_autofocus_device}) ---"
        )
        if crisp1_initial_state == "Idle":
            print(
                f"Attempting to set {hw_interface.crisp_o1_autofocus_device} to '{target_crisp_state}'..."
            )
            if hw_interface.set_crisp_state(
                hw_interface.crisp_o1_autofocus_device, target_crisp_state
            ):
                crisp1_state_changed_to_ready = True  # Mark that we changed it
                time.sleep(1)  # Allow time for state change
                current_state = hw_interface.get_crisp_state(
                    hw_interface.crisp_o1_autofocus_device
                )
                print(f"State after setting to '{target_crisp_state}': {current_state}")

                if current_state == target_crisp_state:
                    print(
                        f"Attempting to set {hw_interface.crisp_o1_autofocus_device} back to 'Idle'..."
                    )
                    if hw_interface.set_crisp_state(
                        hw_interface.crisp_o1_autofocus_device, "Idle"
                    ):
                        crisp1_state_changed_to_ready = (
                            False  # Successfully returned to Idle
                        )
                        time.sleep(0.5)
                        print(
                            f"State after setting back to 'Idle': {hw_interface.get_crisp_state(hw_interface.crisp_o1_autofocus_device)}"
                        )
                    else:
                        print(
                            f"Failed to set {hw_interface.crisp_o1_autofocus_device} back to 'Idle'."
                        )
                elif current_state is not None:
                    print(
                        f"Warning: {hw_interface.crisp_o1_autofocus_device} state is '{current_state}' after attempting to set to '{target_crisp_state}'."
                    )
            else:
                print(
                    f"Failed to set {hw_interface.crisp_o1_autofocus_device} to '{target_crisp_state}'."
                )
        elif crisp1_initial_state is None:
            print(
                f"Could not get initial state for {hw_interface.crisp_o1_autofocus_device}, skipping its state change test."
            )
        else:
            print(
                f"{hw_interface.crisp_o1_autofocus_device} initial state is '{crisp1_initial_state}', not 'Idle'. Skipping '{target_crisp_state}' -> 'Idle' test sequence."
            )

        # --- Test CRISP O3 ---
        print(
            f"\n--- Testing CRISP State Changes ({hw_interface.crisp_o3_autofocus_device}) ---"
        )
        if crisp3_initial_state == "Idle":
            print(
                f"Attempting to set {hw_interface.crisp_o3_autofocus_device} to '{target_crisp_state}'..."
            )
            if hw_interface.set_crisp_state(
                hw_interface.crisp_o3_autofocus_device, target_crisp_state
            ):
                crisp3_state_changed_to_ready = True  # Mark that we changed it
                time.sleep(1)
                current_state = hw_interface.get_crisp_state(
                    hw_interface.crisp_o3_autofocus_device
                )
                print(f"State after setting to '{target_crisp_state}': {current_state}")

                if current_state == target_crisp_state:
                    print(
                        f"Attempting to set {hw_interface.crisp_o3_autofocus_device} back to 'Idle'..."
                    )
                    if hw_interface.set_crisp_state(
                        hw_interface.crisp_o3_autofocus_device, "Idle"
                    ):
                        crisp3_state_changed_to_ready = (
                            False  # Successfully returned to Idle
                        )
                        time.sleep(0.5)
                        print(
                            f"State after setting back to 'Idle': {hw_interface.get_crisp_state(hw_interface.crisp_o3_autofocus_device)}"
                        )
                    else:
                        print(
                            f"Failed to set {hw_interface.crisp_o3_autofocus_device} back to 'Idle'."
                        )
                elif current_state is not None:
                    print(
                        f"Warning: {hw_interface.crisp_o3_autofocus_device} state is '{current_state}' after attempting to set to '{target_crisp_state}'."
                    )
            else:
                print(
                    f"Failed to set {hw_interface.crisp_o3_autofocus_device} to '{target_crisp_state}'."
                )
        elif crisp3_initial_state is None:
            print(
                f"Could not get initial state for {hw_interface.crisp_o3_autofocus_device}, skipping its state change test."
            )
        else:
            print(
                f"{hw_interface.crisp_o3_autofocus_device} initial state is '{crisp3_initial_state}', not 'Idle'. Skipping '{target_crisp_state}' -> 'Idle' test sequence."
            )

        print("\n--- End of CRISP Tests ---")

    except FileNotFoundError as e:
        print(f"Initialization failed due to missing or unconfirmed configuration: {e}")
    except Exception as e:
        print(f"An error occurred during diagnostic test: {e}")
        traceback.print_exc()
    finally:
        if hw_interface:
            # Ensure CRISP devices are set back to Idle if their state might have been changed
            if (
                crisp1_state_changed_to_ready
            ):  # If it was successfully changed to Ready and not back to Idle
                print(
                    f"\nEnsuring {hw_interface.crisp_o1_autofocus_device} is returned to Idle state in finally block..."
                )
                hw_interface.set_crisp_state(
                    hw_interface.crisp_o1_autofocus_device, "Idle"
                )
                print(
                    f"Final {hw_interface.crisp_o1_autofocus_device} State: {hw_interface.get_crisp_state(hw_interface.crisp_o1_autofocus_device)}"
                )

            if (
                crisp3_state_changed_to_ready
            ):  # If it was successfully changed to Ready and not back to Idle
                print(
                    f"\nEnsuring {hw_interface.crisp_o3_autofocus_device} is returned to Idle state in finally block..."
                )
                hw_interface.set_crisp_state(
                    hw_interface.crisp_o3_autofocus_device, "Idle"
                )
                print(
                    f"Final {hw_interface.crisp_o3_autofocus_device} State: {hw_interface.get_crisp_state(hw_interface.crisp_o3_autofocus_device)}"
                )

            print(
                "\nDiagnostic test finished. Hardware not automatically shut down in this example."
            )
