# src/microscope/hardware/hal.py
import os
import time
import traceback
from typing import Any, Optional

from pymmcore_plus import CMMCorePlus

from ..config import HW, USE_DEMO_CONFIG, AcquisitionSettings
from .camera import CameraController
from .galvo import GalvoController
from .plogic import PLogicController
from .stage import StageController

mmc = CMMCorePlus.instance()


class HardwareAbstractionLayer:
    """
    Hardware Abstraction Layer (HAL).

    This class is the single point of entry for controlling the microscope hardware.
    It follows the Facade design pattern, providing a simple, high-level API
    that delegates calls to specialized controller components.
    """

    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_mmc()

        # Compose the HAL from specialized controller components
        # FIX: Correctly pass the required dependencies to each controller
        self.camera = CameraController(mmc, self._set_property)
        self.stage = StageController(mmc, self._set_property)
        self.galvo = GalvoController(self._set_property, self._execute_tiger_serial_command)
        self.plogic = PLogicController(self._execute_tiger_serial_command)

    # --- Public API ---
    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Prepares all hardware for a triggered acquisition sequence."""
        print("\n--- Configuring devices for acquisition ---")
        (
            galvo_amp,
            galvo_center,
            num_slices,
        ) = self._calculate_galvo_parameters(settings)

        self.camera.set_trigger_mode("Edge Trigger")
        self.galvo.configure_for_scan(settings, galvo_amp, galvo_center, num_slices)
        self.stage.configure_for_scan(settings, num_slices)
        self.plogic.program_for_acquisition(settings)
        self.galvo.arm()
        self.stage.set_idle()  # Set piezo to idle after configuration
        print("--- Device configuration finished. ---")

    def start_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        self.galvo.start()

    def final_cleanup(self, settings: AcquisitionSettings):
        """Resets hardware to a safe, idle state after acquisition."""
        print("\n--- Performing final cleanup ---")
        self.galvo.set_idle()
        self.stage.set_idle()
        self.stage.reset_position(settings)
        self.camera.set_trigger_mode("Internal Trigger")

    # --- Private Implementation ---
    def _initialize_mmc(self):
        """Loads hardware configuration from file or demo config."""
        print("Initializing Hardware Abstraction Layer...")
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

    def _execute_tiger_serial_command(self, command_string: str):
        """Executes a serial command on the TigerCommHub."""
        if USE_DEMO_CONFIG:
            print(f"DEMO MODE: Skipping serial command: {command_string}")
            return

        hub = HW.tiger_comm_hub_label
        if hub not in mmc.getLoadedDevices() or not mmc.hasProperty(hub, "SerialCommand"):
            print(f"Warning: Cannot send serial commands to '{hub}'.")
            return

        original = mmc.getProperty(hub, "OnlySendSerialCommandOnChange")
        if original == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "No")

        mmc.setProperty(hub, "SerialCommand", command_string)

        if original == "Yes":
            mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")
        time.sleep(0.02)

    def _set_property(self, device_label: str, prop_name: str, value: Any):
        """Safely sets a property on a device if it has changed."""
        if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, prop_name):
            if mmc.getProperty(device_label, prop_name) != str(value):
                mmc.setProperty(device_label, prop_name, value)
        elif not USE_DEMO_CONFIG:
            print(f"Warning: Cannot set '{prop_name}' for '{device_label}'.")

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
