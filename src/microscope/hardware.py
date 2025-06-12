# src/microscope/hardware.py
"""
Hardware Controller Module

This module abstracts all direct hardware communication with the microscope.
It provides a clean, high-level API for the acquisition engine to use,
without exposing the underlying `pymmcore-plus` details.
"""

from pymmcore_plus import CMMCorePlus

from .settings import AcquisitionSettings, HardwareConstants


class HardwareController:
    """A class to encapsulate all hardware control logic."""

    def __init__(self, mmc: CMMCorePlus, const: HardwareConstants):
        """
        Initializes the HardwareController.

        Args:
            mmc: The pymmcore-plus instance.
            const: The HardwareConstants data object.
        """
        self.mmc = mmc
        self.const = const

        # --- FIX: Detect if we are running with demo/dummy devices ---
        # This allows us to bypass commands that would fail on dummy hardware.
        try:
            hub_lib = self.mmc.getDeviceLibrary(self.const.TIGER_COMM_HUB_LABEL)
            self.is_demo = hub_lib == "Utilities"
        except Exception:
            # Fallback in case the hub isn't loaded for some reason
            self.is_demo = False

        if self.is_demo:
            print("HardwareController initialized in DEMO mode.")

    def _execute_tiger_serial_command(self, command: str):
        """Sends a raw serial command to the Tiger controller."""
        # --- FIX: Do not send serial commands in demo mode ---
        if self.is_demo:
            print(f"[DEMO] Skipping serial command: {command}")
            return

        hub = self.const.TIGER_COMM_HUB_LABEL
        # Temporarily disable 'OnlySendSerialCommandOnChange' for this command
        original_setting = self.mmc.getProperty(hub, "OnlySendSerialCommandOnChange")
        if original_setting == "Yes":
            self.mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "No")
        self.mmc.setProperty(hub, "SerialCommand", command)
        if original_setting == "Yes":
            self.mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")
        self.mmc.waitForDevice(hub)

    def _set_property(self, device_label: str, prop: str, value):
        """Safely sets a property on a device if it exists and has changed."""
        if self.mmc.hasProperty(device_label, prop):
            if self.mmc.getProperty(device_label, prop) != str(value):
                self.mmc.setProperty(device_label, prop, value)
        else:
            # This is expected in demo mode for many properties
            print(f"Warn: Property '{prop}' not found on device '{device_label}'.")

    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Configures all devices for a triggered Z-stack acquisition."""
        print("Configuring devices for acquisition...")
        self._configure_plogic(settings)
        self._configure_galvo_and_piezo(settings)
        self.find_and_set_trigger_mode("Edge Trigger")

    def _configure_plogic(self, settings: AcquisitionSettings):
        """Programs the PLogic card for timed laser and camera pulses."""
        plogic_addr = self.const.PLOGIC_LABEL[-2:]

        cmd = f"{plogic_addr}CCA X={self.const.PLOGIC_LASER_PRESET_NUM}"
        self._execute_tiger_serial_command(cmd)
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_LASER_ON_CELL}")
        self._execute_tiger_serial_command("CCA Y=14")  # one-shot mode
        cycles = int(settings.laser_trig_duration_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")
        cam_ttl = self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR
        clock_addr = self.const.PLOGIC_4KHZ_CLOCK_ADDR
        cmd = f"CCB X={cam_ttl} Y={clock_addr}"
        self._execute_tiger_serial_command(cmd)

    def _configure_galvo_and_piezo(self, settings: AcquisitionSettings):
        """Calculates and sets galvo/piezo parameters for the Z-stack."""
        slope = self.const.SLICE_CALIBRATION_SLOPE_UM_PER_DEG
        offset = self.const.SLICE_CALIBRATION_OFFSET_UM
        if abs(slope) < 1e-9:
            raise ValueError("Slice calibration slope cannot be zero.")

        piezo_amplitude = (settings.num_slices - 1) * settings.step_size_um
        galvo_amplitude = piezo_amplitude / slope
        galvo_center = (self.const.PIEZO_CENTER_UM - offset) / slope

        galvo = self.const.GALVO_A_LABEL
        self._set_property(galvo, "SPIMNumSlices", settings.num_slices)
        self._set_property(galvo, "SingleAxisYAmplitude(deg)", round(galvo_amplitude, 4))
        self._set_property(galvo, "SingleAxisYOffset(deg)", round(galvo_center, 4))

        piezo = self.const.PIEZO_A_LABEL
        self._set_property(piezo, "SPIMNumSlices", settings.num_slices)
        self._set_property(piezo, "SingleAxisAmplitude(um)", 0.0)
        self._set_property(piezo, "SingleAxisOffset(um)", self.const.PIEZO_CENTER_UM)

        self._set_property(piezo, "SPIMState", "Armed")
        self._set_property(galvo, "SPIMState", "Armed")

    def trigger_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        print("Triggering acquisition...")
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Running")

    def get_pixel_size_um(self) -> float:
        """Returns the camera pixel size from Micro-Manager."""
        try:
            return self.mmc.getPixelSizeUm()
        except Exception:
            print("Warning: Could not get pixel size. Defaulting to 1.0 µm.")
            return 1.0

    def find_and_set_trigger_mode(self, mode: str) -> bool:
        """Sets the camera trigger mode (e.g., 'Internal' or 'Edge Trigger')."""
        if self.is_demo:
            print("[DEMO] Skipping trigger mode setting.")
            return True

        cam = self.const.CAMERA_A_LABEL
        if not self.mmc.hasProperty(cam, "TriggerMode"):
            return True  # Not all cameras have this property

        allowed = self.mmc.getAllowedPropertyValues(cam, "TriggerMode")
        if mode in allowed:
            self._set_property(cam, "TriggerMode", mode)
            return True
        print(f"Warn: Mode '{mode}' not supported. Allowed: {allowed}")
        return False

    def final_cleanup(self):
        """Resets hardware to a safe, idle state after acquisition."""
        print("Performing final hardware cleanup...")
        galvo = self.const.GALVO_A_LABEL
        piezo = self.const.PIEZO_A_LABEL
        self._set_property(galvo, "BeamEnabled", "No")
        self._set_property(galvo, "SPIMState", "Idle")
        self._set_property(piezo, "SPIMState", "Idle")
        self._set_property(piezo, "SingleAxisOffset(um)", self.const.PIEZO_CENTER_UM)
        self.find_and_set_trigger_mode("Internal")
