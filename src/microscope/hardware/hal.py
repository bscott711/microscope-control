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
        self.camera = CameraController(mmc, self._set_property)
        self.stage = StageController(mmc, self._set_property)
        self.galvo = GalvoController(self._set_property)
        self.plogic = PLogicController(self._execute_tiger_serial_command)

    # --- Public API ---
    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Prepares all hardware for a triggered acquisition sequence."""
        print("\n--- Configuring devices for acquisition (standard path) ---")
        self.camera.set_trigger_mode("Edge Trigger")
        self.galvo.configure_for_scan(settings)
        self.stage.configure_for_scan(settings)
        self.plogic.program_for_acquisition(settings)
        self.stage.set_idle()
        print("--- Device configuration finished. ---")

    def start_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        self.galvo.start()

    def final_cleanup(self, settings: AcquisitionSettings):
        """Resets hardware to a safe, idle state after acquisition."""
        print("\n--- Performing final cleanup (standard path) ---")
        self.galvo.set_idle()
        self.stage.set_idle()
        self.plogic.cleanup()
        self.stage.reset_position(settings)
        self.camera.set_trigger_mode("Internal Trigger")

    def run_validated_test(self, settings: AcquisitionSettings):
        """
        Runs a self-contained test acquisition using the exact sequence
        derived from the validated Micro-Manager log file. This bypasses
        the main controller classes for debugging purposes.
        """
        print("\n--- Starting Validated Test Sequence ---")
        initial_camera = mmc.getCameraDevice()
        initial_auto_shutter = mmc.getAutoShutter()
        initial_exposure = mmc.getExposure()
        initial_trigger_mode = "Internal Trigger"  # Default value

        try:
            # 1. Setup
            print(f"Validated Test: Setting active camera to {self.camera.label}")
            mmc.setCameraDevice(self.camera.label)

            # Now that Camera-1 is active, get its initial trigger mode
            initial_trigger_mode = self.camera.mmc.getProperty(self.camera.label, "TriggerMode")

            mmc.setAutoShutter(False)
            mmc.setConfig("Lasers", "488nm")
            self.camera.set_trigger_mode("Edge Trigger")
            mmc.setExposure(settings.camera_exposure_ms)
            self.galvo.configure_for_scan(settings)
            self.plogic.program_for_acquisition(settings)
            mmc.waitForSystem()
            print("Validated Test: Devices configured.")

            # 2. Execution
            mmc.startSequenceAcquisition(self.camera.label, settings.num_slices, 0, True)
            self.galvo.start()
            while mmc.isSequenceRunning(self.camera.label):
                time.sleep(0.05)
            print("Validated Test: Sequence complete.")

        finally:
            # 3. Cleanup
            print("Validated Test: Cleaning up...")
            if mmc.isSequenceRunning(self.camera.label):
                mmc.stopSequenceAcquisition(self.camera.label)

            self.galvo.set_idle()
            self.stage.set_idle()
            self.plogic.cleanup()
            self.camera.set_trigger_mode(initial_trigger_mode)
            mmc.setExposure(initial_exposure)
            mmc.setAutoShutter(initial_auto_shutter)

            # --- FIX: Reordered cleanup sequence ---
            # 1. Wait for the system to be idle WHILE Camera-1 is still active.
            mmc.waitForSystem()

            # 2. THEN restore the original camera device as the very last step.
            print(f"Validated Test: Restoring active camera to {initial_camera}")
            mmc.setCameraDevice(initial_camera)

            print("--- Validated Test Finished ---")

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
