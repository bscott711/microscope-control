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
    Hardware Abstraction Layer (HAL).

    Encapsulates all direct hardware control and configuration logic,
    providing a high-level API for other parts of the application.
    """

    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    # Public API Methods
    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Prepares all hardware for a triggered acquisition sequence."""
        print("\n--- Configuring devices for acquisition ---")
        (
            galvo_amp,
            galvo_center,
            num_slices,
        ) = self._calculate_galvo_parameters(settings)

        self._configure_camera()
        self._configure_galvo(settings, galvo_amp, galvo_center, num_slices)
        self._configure_piezo(settings, num_slices)
        self._configure_plogic(settings)
        self._arm_devices()
        print("--- Device configuration finished. ---")

    def start_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        print(">>> Sending master trigger to start acquisition...")
        self._set_property(HW.galvo_a_label, "SPIMState", "Running")
        print(">>> Master trigger sent.")

    def final_cleanup(self, settings: AcquisitionSettings):
        """Resets hardware to a safe, idle state after acquisition."""
        print("\n--- Performing final cleanup ---")
        self._set_property(HW.galvo_a_label, "BeamEnabled", "No")
        self._set_property(HW.galvo_a_label, "SPIMState", "Idle")
        self._set_property(HW.piezo_a_label, "SPIMState", "Idle")
        self._set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)
        self._find_and_set_trigger_mode(self.camera1, ["Internal Trigger"])

    # Private Helper Methods
    def _initialize_hardware(self):
        """Loads hardware configuration from file or demo config."""
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
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        print(f"Attempting to load configuration: '{self.config_path}'")
        try:
            mmc.loadSystemConfiguration(self.config_path)
            print("Configuration loaded successfully.")
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{self.config_path}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        return HW.camera_a_label

    def _calculate_galvo_parameters(self, settings: AcquisitionSettings):
        """Calculates galvo scan parameters from acquisition settings."""
        if abs(HW.slice_calibration_slope_um_per_deg) < 1e-9:
            raise ValueError("Slice calibration slope cannot be zero.")
        num_slices = settings.num_slices
        piezo_amplitude = (num_slices - 1) * settings.step_size_um
        if HW.camera_mode_is_overlap:
            if num_slices > 1:
                piezo_amplitude *= float(num_slices) / (num_slices - 1.0)
            num_slices += 1

        galvo_amplitude = piezo_amplitude / HW.slice_calibration_slope_um_per_deg
        galvo_center = (
            settings.piezo_center_um - HW.slice_calibration_offset_um
        ) / HW.slice_calibration_slope_um_per_deg
        return round(galvo_amplitude, 4), round(galvo_center, 4), num_slices

    def _configure_camera(self):
        """Sets the camera to the correct trigger mode for acquisition."""
        self._find_and_set_trigger_mode(self.camera1, ["Edge Trigger"])

    def _configure_galvo(self, settings, galvo_amplitude_deg, galvo_center_deg, num_slices):
        """Configures all properties of the galvo scanner card."""
        print("Configuring Galvo scanner...")
        galvo = HW.galvo_a_label
        galvo_card_addr = galvo.split(":")[2]

        self._execute_tiger_serial_command(f"{galvo_card_addr}TTL X=2 Y=1")
        self._set_property(galvo, "BeamEnabled", "Yes")
        self._set_property(galvo, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
        self._set_property(galvo, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
        self._set_property(galvo, "SPIMNumRepeats", 1)
        self._set_property(galvo, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
        self._set_property(galvo, "SPIMAlternateDirectionsEnable", "Yes" if HW.scan_opposite_directions else "No")
        self._set_property(galvo, "SPIMScanDuration(ms)", settings.camera_exposure_ms)
        self._set_property(galvo, "SingleAxisYAmplitude(deg)", galvo_amplitude_deg)
        self._set_property(galvo, "SingleAxisYOffset(deg)", galvo_center_deg)
        self._set_property(galvo, "SPIMNumSlices", num_slices)
        self._set_property(galvo, "SPIMNumSides", HW.num_sides)
        self._set_property(galvo, "SPIMFirstSide", "A" if HW.first_side_is_a else "B")
        self._set_property(galvo, "SPIMPiezoHomeDisable", "Yes")
        self._set_property(galvo, "SPIMInterleaveSidesEnable", "No")
        self._set_property(galvo, "SingleAxisXAmplitude(deg)", HW.sheet_width_deg)
        self._set_property(galvo, "SingleAxisXOffset(deg)", HW.sheet_offset_deg)

    def _configure_piezo(self, settings, num_slices):
        """Configures all properties of the piezo stage card."""
        print("Configuring Piezo stage...")
        piezo = HW.piezo_a_label
        piezo_fixed_pos = round(settings.piezo_center_um, 3)
        self._set_property(piezo, "SingleAxisAmplitude(um)", 0.0)
        self._set_property(piezo, "SingleAxisOffset(um)", piezo_fixed_pos)
        self._set_property(piezo, "SPIMNumSlices", num_slices)

    def _configure_plogic(self, settings: AcquisitionSettings):
        """Programs the PLogic card for timed camera and laser pulses."""
        print("Configuring PLogic card...")
        addr = HW.plogic_label[-2:]

        self._execute_tiger_serial_command(f"{addr}RM F")
        self._execute_tiger_serial_command(f"{addr}RM Z")

        # Configure camera delay/pulse
        delay = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{addr}M E={HW.PLOGIC_CELL_CAMERA_DELAY}")
        self._execute_tiger_serial_command(f"{addr}CCA Y=13")
        self._execute_tiger_serial_command(f"{addr}CCA Z={delay}")
        self._execute_tiger_serial_command(f"{addr}CCB X={HW.PLOGIC_INPUT_GALVO} Y={HW.PLOGIC_INPUT_CLOCK}")

        # Configure laser delay
        delay = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{addr}M E={HW.PLOGIC_CELL_LASER_DELAY}")
        self._execute_tiger_serial_command(f"{addr}CCA Y=13")
        self._execute_tiger_serial_command(f"{addr}CCA Z={delay}")
        self._execute_tiger_serial_command(f"{addr}CCB X={HW.PLOGIC_INPUT_GALVO} Y={HW.PLOGIC_INPUT_CLOCK}")

        # Configure laser pulse duration
        duration = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
        self._execute_tiger_serial_command(f"{addr}M E={HW.PLOGIC_CELL_LASER_PULSE}")
        self._execute_tiger_serial_command(f"{addr}CCA Y=14")
        self._execute_tiger_serial_command(f"{addr}CCA Z={duration}")
        self._execute_tiger_serial_command(f"{addr}CCB X={128 + HW.PLOGIC_CELL_LASER_DELAY} Y={HW.PLOGIC_INPUT_CLOCK}")

        # Route cell outputs to physical TTL outputs
        self._execute_tiger_serial_command(f"{addr}TTL X={HW.PLOGIC_OUTPUT_CAMERA} Y=8")
        self._execute_tiger_serial_command(f"{addr}TTL X={HW.PLOGIC_OUTPUT_LASER} Y=8")
        self._execute_tiger_serial_command(f"{addr}M E={HW.PLOGIC_OUTPUT_CAMERA}")
        self._execute_tiger_serial_command(f"{addr}CCA Y=1")
        self._execute_tiger_serial_command(f"{addr}CCB X={HW.PLOGIC_CELL_CAMERA_DELAY}")
        self._execute_tiger_serial_command(f"{addr}M E={HW.PLOGIC_OUTPUT_LASER}")
        self._execute_tiger_serial_command(f"{addr}CCA Y=1")
        self._execute_tiger_serial_command(f"{addr}CCB X={HW.PLOGIC_CELL_LASER_PULSE}")

    def _arm_devices(self):
        """Arms the relevant state machines on the controller cards."""
        print("Arming devices...")
        self._set_property(HW.galvo_a_label, "SPIMState", "Armed")

    def _wait_for_tiger_ready(self, timeout_s: float = 5.0):
        hub = HW.tiger_comm_hub_label
        response = ""
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_s:
            mmc.setProperty(hub, "SerialCommand", "STATUS")
            time.sleep(0.01)
            response = mmc.getProperty(hub, "SerialResponse")
            if "N" in response:
                return True
            time.sleep(0.05)
        print(f"WARNING: Timeout waiting for Tiger. Last response: {response}")
        return False

    def _execute_tiger_serial_command(self, command_string: str):
        if USE_DEMO_CONFIG:
            print(f"SERIAL COMMAND: {command_string}")
            return

        hub = HW.tiger_comm_hub_label
        if hub not in mmc.getLoadedDevices():
            return
        original_setting = mmc.getProperty(hub, "OnlySendSerialCommandOnChange")
        if original_setting == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "No")

        if self._wait_for_tiger_ready():
            print(f"SERIAL COMMAND: {command_string}")
            mmc.setProperty(hub, "SerialCommand", command_string)
            time.sleep(0.02)

        if original_setting == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")

    def _set_property(self, device_label: str, property_name: str, value: Any):
        if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
            current_value = mmc.getProperty(device_label, property_name)
            str_value = str(value)
            needs_update = True
            try:
                if math.isclose(float(current_value), float(str_value), rel_tol=1e-5):
                    needs_update = False
            except (ValueError, TypeError):
                if current_value == str_value:
                    needs_update = False

            if needs_update:
                mmc.setProperty(device_label, property_name, value)

    def _find_and_set_trigger_mode(self, camera_label: str, modes: list[str]) -> bool:
        if USE_DEMO_CONFIG or camera_label not in mmc.getLoadedDevices():
            return True
        prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, prop):
            return True
        try:
            allowed = mmc.getAllowedPropertyValues(camera_label, prop)
            for mode in modes:
                if mode in allowed:
                    self._set_property(camera_label, prop, mode)
                    return True
            print(f"Warning: Could not set trigger mode. Allowed: {allowed}")
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
