# microscope/hardware_control.py
import math
import os
import time
import traceback
from typing import Any, Optional

from pymmcore_plus import CMMCorePlus

from .config import HW, USE_DEMO_CONFIG, AcquisitionSettings

mmc = CMMCorePlus.instance()


class HardwareInterface:
    """
    Encapsulates all direct hardware control and configuration logic.
    This class provides a high-level API for the acquisition worker.
    """

    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        """Loads the hardware configuration from the provided file."""
        print("Initializing HardwareInterface...")
        if USE_DEMO_CONFIG:
            try:
                self._load_demo_config()
                return
            except Exception as e:
                print(f"CRITICAL Error loading DEMO configuration: {e}")
                traceback.print_exc()
                raise

        if not self.config_path or not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Hardware config file not found at '{self.config_path}'")

        print(f"Attempting to load configuration: '{self.config_path}'")
        try:
            mmc.loadSystemConfiguration(self.config_path)
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{self.config_path}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        """Returns the device label for the primary camera."""
        return HW.camera_a_label

    def _wait_for_tiger_ready(self, timeout_s: float = 5.0):
        """Polls the 'STATUS' of the Tiger controller until it is not busy."""
        hub = HW.tiger_comm_hub_label
        start_time = time.monotonic()
        response = ""  # Initialize response to prevent unbound variable error
        while time.monotonic() - start_time < timeout_s:
            mmc.setProperty(hub, "SerialCommand", "STATUS")
            time.sleep(0.01)  # Brief pause for command to be processed
            response = mmc.getProperty(hub, "SerialResponse")
            if "N" in response:  # 'N' signifies "Not busy"
                return True
            time.sleep(0.05)  # Wait longer before next poll
        print(f"WARNING: Timeout waiting for Tiger controller to be ready. Last response: {response}")
        return False

    def _execute_tiger_serial_command(self, command_string: str):
        """Waits for the Tiger to be ready, then sends a serial command."""
        if USE_DEMO_CONFIG:
            print(f"SERIAL COMMAND: {command_string}")
            return

        hub = HW.tiger_comm_hub_label
        if hub not in mmc.getLoadedDevices() or not mmc.hasProperty(hub, "SerialCommand"):
            print(f"Warning: Cannot send serial commands to '{hub}'. Device or 'SerialCommand' property not found.")
            return

        original_setting = mmc.getProperty(hub, "OnlySendSerialCommandOnChange")
        if original_setting == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "No")

        # Wait for the controller to be ready before sending the command
        if self._wait_for_tiger_ready():
            print(f"SERIAL COMMAND: {command_string}")
            mmc.setProperty(hub, "SerialCommand", command_string)
            time.sleep(0.02)  # Small delay for command to process

        if original_setting == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")

    def _set_property(self, device_label: str, property_name: str, value: Any):
        """Safely sets a property and verifies it by reading it back."""
        if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
            current_value = mmc.getProperty(device_label, property_name)
            str_value = str(value)

            # Check if the property needs updating
            needs_update = True
            try:
                # Use a tolerance for floating-point comparisons
                if math.isclose(float(current_value), float(str_value), rel_tol=1e-5):
                    needs_update = False
            except (ValueError, TypeError):
                # Fallback to string comparison for non-numeric properties
                if current_value == str_value:
                    needs_update = False

            if needs_update:
                print(f"  - Setting {device_label}:{property_name} from '{current_value}' to '{str_value}'")
                mmc.setProperty(device_label, property_name, value)
                time.sleep(0.01)  # Give hardware time to process
                read_back_value = mmc.getProperty(device_label, property_name)

                # Verify the read-back value with the same logic
                verified = False
                try:
                    if math.isclose(float(read_back_value), float(str_value), rel_tol=1e-5):
                        verified = True
                except (ValueError, TypeError):
                    if read_back_value == str_value:
                        verified = True

                if verified:
                    print(f"    L VERIFIED: {device_label}:{property_name} is now '{read_back_value}'.")
                else:
                    print(f"    L WARNING: Read-back value '{read_back_value}' does not match set value '{str_value}'.")

        elif not USE_DEMO_CONFIG:
            print(f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found.")

    def _configure_plogic_for_acquisition(self, settings: AcquisitionSettings):
        """Configures the PLogic card using a direct timing model."""
        plogic_dev_addr = HW.plogic_label[-2:]
        galvo_trigger = HW.galvo_trigger_addr
        clock = HW.clock_source_addr

        self._execute_tiger_serial_command(f"{plogic_dev_addr}RM F")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}RM Z")

        delay_cycles_cam = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.camera_delay_cell}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=13")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={delay_cycles_cam}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={galvo_trigger} Y={clock}")

        laser_delay_cell = 11
        delay_cycles_laser = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{plogic_dev_addr}M E={laser_delay_cell}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=13")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={delay_cycles_laser}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={galvo_trigger} Y={clock}")

        pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.laser_on_cell}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=14")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={pulse_duration_cycles}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={128 + laser_delay_cell} Y={clock}")

        self._execute_tiger_serial_command(f"{plogic_dev_addr}TTL X={HW.camera_trigger_addr} Y=8")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}TTL X={HW.laser_trigger_addr} Y=8")

        self._execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.camera_trigger_addr}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=1")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={HW.camera_delay_cell}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.laser_trigger_addr}")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=1")
        self._execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={HW.laser_on_cell}")
        print("PLogic card configured for acquisition.")

    def calculate_galvo_parameters(self, settings: AcquisitionSettings):
        """Calculates galvo scan parameters based on acquisition settings."""
        if abs(HW.slice_calibration_slope_um_per_deg) < 1e-9:
            raise ValueError("Slice calibration slope cannot be zero.")
        num_slices_ctrl = settings.num_slices
        piezo_amplitude_um = (num_slices_ctrl - 1) * settings.step_size_um
        if HW.camera_mode_is_overlap:
            if num_slices_ctrl > 1:
                piezo_amplitude_um *= float(num_slices_ctrl) / (num_slices_ctrl - 1.0)
            num_slices_ctrl += 1
        galvo_slice_amplitude_deg = piezo_amplitude_um / HW.slice_calibration_slope_um_per_deg
        galvo_slice_center_deg = (
            settings.piezo_center_um - HW.slice_calibration_offset_um
        ) / HW.slice_calibration_slope_um_per_deg
        return (
            round(galvo_slice_amplitude_deg, 4),
            round(galvo_slice_center_deg, 4),
            num_slices_ctrl,
        )

    def configure_devices_for_slice_scan(
        self,
        settings: AcquisitionSettings,
        galvo_amplitude_deg: float,
        galvo_center_deg: float,
        num_slices_ctrl: int,
    ):
        """Configures all devices for a hardware-triggered slice scan."""
        print("\n--- Configuring devices for slice scan ---")
        piezo_fixed_pos_um = round(settings.piezo_center_um, 3)

        print("Step 1: Setting device properties...")
        self.find_and_set_trigger_mode(self.camera1, ["Edge Trigger"])

        # FIX: Tell the Galvo to output a trigger on backplane TTL 2 (for PLogic)
        galvo_card_addr = HW.galvo_a_label.split(":")[2]
        self._execute_tiger_serial_command(f"{galvo_card_addr}TTL X=2 Y=1")

        self._set_property(HW.galvo_a_label, "BeamEnabled", "Yes")
        self._set_property(HW.galvo_a_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
        self._set_property(HW.galvo_a_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
        self._set_property(HW.galvo_a_label, "SPIMNumRepeats", 1)
        self._set_property(HW.galvo_a_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
        self._set_property(
            HW.galvo_a_label,
            "SPIMAlternateDirectionsEnable",
            "Yes" if HW.scan_opposite_directions else "No",
        )
        self._set_property(HW.galvo_a_label, "SPIMScanDuration(ms)", settings.camera_exposure_ms)
        self._set_property(HW.galvo_a_label, "SingleAxisYAmplitude(deg)", galvo_amplitude_deg)
        self._set_property(HW.galvo_a_label, "SingleAxisYOffset(deg)", galvo_center_deg)
        self._set_property(HW.galvo_a_label, "SPIMNumSlices", num_slices_ctrl)
        self._set_property(HW.galvo_a_label, "SPIMNumSides", HW.num_sides)
        self._set_property(HW.galvo_a_label, "SPIMFirstSide", "A" if HW.first_side_is_a else "B")
        self._set_property(HW.galvo_a_label, "SPIMPiezoHomeDisable", "Yes")
        self._set_property(HW.galvo_a_label, "SPIMInterleaveSidesEnable", "No")
        self._set_property(HW.galvo_a_label, "SingleAxisXAmplitude(deg)", HW.sheet_width_deg)
        self._set_property(HW.galvo_a_label, "SingleAxisXOffset(deg)", HW.sheet_offset_deg)

        self._set_property(HW.piezo_a_label, "SingleAxisAmplitude(um)", 0.0)
        self._set_property(HW.piezo_a_label, "SingleAxisOffset(um)", piezo_fixed_pos_um)
        self._set_property(HW.piezo_a_label, "SPIMNumSlices", num_slices_ctrl)

        print("Step 2: Configuring PLogic...")
        self._configure_plogic_for_acquisition(settings)

        print("Step 3: Arming devices...")
        self._set_property(HW.galvo_a_label, "SPIMState", "Armed")
        print("--- Device configuration finished. ---")

    def trigger_slice_scan_acquisition(self):
        """Sends the master trigger to the galvo to start the scan."""
        print(">>> Sending master trigger to start acquisition...")
        self._set_property(HW.galvo_a_label, "SPIMState", "Running")
        print(">>> Master trigger sent.")

    def _reset_for_next_volume(self):
        """Resets the controller state between time points."""
        print("Resetting controller state for next volume...")
        self._set_property(HW.galvo_a_label, "BeamEnabled", "No")
        self._set_property(HW.galvo_a_label, "SPIMState", "Idle")
        self._set_property(HW.piezo_a_label, "SPIMState", "Idle")

    def final_cleanup(self, settings: AcquisitionSettings):
        """Performs final cleanup after the entire acquisition is done."""
        print("Performing final cleanup...")
        self._reset_for_next_volume()
        self._set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)
        self.find_and_set_trigger_mode(self.camera1, ["Internal Trigger"])

    def find_and_set_trigger_mode(self, camera_label: str, desired_modes: list[str]) -> bool:
        """Finds and sets the first available trigger mode from a list."""
        if USE_DEMO_CONFIG or camera_label not in mmc.getLoadedDevices():
            return True
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            print(f"Info: Camera '{camera_label}' does not have a 'TriggerMode' property.")
            return True  # Not an error
        try:
            allowed = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
            for mode in desired_modes:
                if mode in allowed:
                    self._set_property(camera_label, "TriggerMode", mode)
                    return True
            print(f"Warning: Could not set desired trigger mode. Allowed: {allowed}")
            return False
        except Exception:
            return False

    def _load_demo_config(self):
        """Programmatically loads a demo configuration for testing."""
        print("Programmatically loading DEMO configuration...")
        mmc.loadDevice(HW.camera_a_label, "DemoCamera", "DCam")
        mmc.loadDevice(HW.piezo_a_label, "DemoCamera", "DStage")
        mmc.loadDevice(HW.galvo_a_label, "DemoCamera", "DXYStage")
        mmc.loadDevice(HW.tiger_comm_hub_label, "DemoCamera", "DShutter")
        mmc.loadDevice(HW.plogic_label, "DemoCamera", "DShutter")
        mmc.initializeAllDevices()
        mmc.setFocusDevice(HW.piezo_a_label)
        mmc.definePixelSizeConfig("px")
        mmc.setPixelSizeUm("px", 1.0)
