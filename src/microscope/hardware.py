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
        self.initial_galvo_y_offset: float = 0.0
        self.is_demo: bool = False
        self._check_for_demo_mode()

    def _check_for_demo_mode(self):
        """Checks if the controller is running with dummy/demo devices."""
        try:
            hub_lib = self.mmc.getDeviceLibrary(self.const.TIGER_COMM_HUB_LABEL)
            self.is_demo = hub_lib == "Utilities"
        except Exception:
            self.is_demo = True  # Assume demo if hub not found
        if self.is_demo:
            print("HardwareController initialized in DEMO mode.")

    def _execute_tiger_serial_command(self, command: str):
        """Sends a raw serial command to the Tiger controller."""
        if self.is_demo:
            print(f"[DEMO] Skipping serial command: {command}")
            return

        hub = self.const.TIGER_COMM_HUB_LABEL
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
            print(f"Warn: Property '{prop}' not found on device '{device_label}'.")

    # --- Acquisition Methods ---

    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Configures all devices for a triggered Z-stack acquisition."""
        print("Configuring devices for acquisition...")
        self.mmc.setExposure(settings.camera_exposure_ms)
        self._configure_plogic(settings)
        self._configure_galvo_for_scan(settings)
        self._arm_spim_devices()
        self.find_and_set_trigger_mode("Edge Trigger")

    def _configure_plogic(self, settings: AcquisitionSettings):
        """Programs the PLogic card for timed laser and camera pulses."""
        plogic_addr = self.const.PLOGIC_LABEL[-2:]

        cmd = f"{plogic_addr}CCA X={self.const.PLOGIC_LASER_PRESET_NUM}"
        self._execute_tiger_serial_command(cmd)
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_LASER_ON_CELL}")
        self._execute_tiger_serial_command("CCA Y=14")
        cycles = int(settings.laser_trig_duration_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")

        cam_ttl = self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR
        clock_addr = self.const.PLOGIC_4KHZ_CLOCK_ADDR
        cmd = f"CCB X={cam_ttl} Y={clock_addr}"
        self._execute_tiger_serial_command(cmd)

    def _configure_galvo_for_scan(self, settings: AcquisitionSettings):
        """Calculates and sets galvo parameters for a Z-stack."""
        galvo = self.const.GALVO_A_LABEL
        slope = self.const.SLICE_CALIBRATION_SLOPE_UM_PER_DEG
        if abs(slope) < 1e-9:
            raise ValueError("Slice calibration slope cannot be zero.")

        try:
            current_offset_deg_str = self.mmc.getProperty(
                galvo, "SingleAxisYOffset(deg)"
            )
            current_galvo_offset_deg = float(current_offset_deg_str)
        except Exception:
            print("Warn: Could not get galvo offset. Defaulting to 0 for demo mode.")
            current_galvo_offset_deg = 0.0
        self.initial_galvo_y_offset = current_galvo_offset_deg

        piezo_equivalent_travel = (settings.num_slices - 1) * settings.step_size_um
        galvo_amplitude_deg = piezo_equivalent_travel / slope

        self._set_property(galvo, "SPIMNumSlices", settings.num_slices)
        self._set_property(
            galvo, "SingleAxisYAmplitude(deg)", round(galvo_amplitude_deg, 4)
        )
        self._set_property(
            galvo, "SingleAxisYOffset(deg)", round(current_galvo_offset_deg, 4)
        )

    def _arm_spim_devices(self):
        """Sets the SPIM state of relevant devices to 'Armed'."""
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Armed")

    def trigger_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        print("Triggering acquisition...")
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Running")

    def final_cleanup(self):
        """Resets hardware to a safe, idle state after acquisition."""
        print("Performing final hardware cleanup...")
        galvo = self.const.GALVO_A_LABEL
        self._set_property(galvo, "BeamEnabled", "No")
        self._set_property(galvo, "SPIMState", "Idle")
        self._set_property(galvo, "SingleAxisYOffset(deg)", self.initial_galvo_y_offset)
        self.find_and_set_trigger_mode("Internal Trigger")

    # --- Live Scan & Navigation Methods ---

    def start_live_scan(self, exposure_ms: float):
        """Starts a continuous 'live' camera acquisition."""
        print(f"Starting live scan with {exposure_ms}ms exposure.")
        self.mmc.setExposure(exposure_ms)
        self.mmc.startContinuousSequenceAcquisition(0)

    def stop_live_scan(self):
        """Stops the continuous 'live' camera acquisition."""
        print("Stopping live scan.")
        if self.mmc.isSequenceRunning():
            self.mmc.stopSequenceAcquisition()

    def get_position(self, device_label: str) -> float:
        """Gets the current position of a 1D stage."""
        return self.mmc.getPosition(device_label)

    def set_position(self, device_label: str, position: float):
        """Moves a 1D stage to an absolute position and waits for it to arrive."""
        print(f"Moving {device_label} to {position}...")
        self.mmc.setPosition(device_label, position)
        self.mmc.waitForDevice(device_label)
        print("Move complete.")

    def set_relative_position(self, device_label: str, offset: float):
        """Moves a 1D stage by a relative offset."""
        current_pos = self.get_position(device_label)
        self.set_position(device_label, current_pos + offset)

    def get_all_positions(self) -> dict[str, float]:
        """Queries and returns the positions of all primary navigation axes."""
        positions = {}
        try:
            x = self.mmc.getXPosition(self.const.XY_STAGE_LABEL)
            y = self.mmc.getYPosition(self.const.XY_STAGE_LABEL)
            positions["XY-X"] = x
            positions["XY-Y"] = y
        except Exception:
            positions["XY-X"] = 0.0
            positions["XY-Y"] = 0.0

        try:
            positions["Z-Piezo"] = self.get_position(self.const.Z_PIEZO_LABEL)
            positions["Z-Stage"] = self.get_position(self.const.Z_STAGE_LABEL)
            positions["Filter-Z"] = self.get_position(self.const.FILTER_Z_STAGE_LABEL)
        except Exception:
            positions["Z-Piezo"] = 0.0
            positions["Z-Stage"] = 0.0
            positions["Filter-Z"] = 0.0
        return positions

    # --- NEW: Jogging Methods ---
    def start_jog(self, device_label: str, speed_microns_per_sec: float):
        """Starts jogging a stage continuously."""
        print(f"Jogging {device_label} at {speed_microns_per_sec} µm/s")
        # Note: The real implementation might require specific serial commands
        # to the Tiger controller. This is a placeholder for that logic.
        if self.is_demo:
            print("[DEMO] Jogging started.")

    def stop_jog(self, device_label: str):
        """Stops jogging a specific stage."""
        print(f"Stopping jog for {device_label}")
        if self.is_demo:
            print("[DEMO] Jogging stopped.")

    def stop_all_stages(self):
        """Stops all movement on all stages."""
        print("STOPPING ALL STAGE MOVEMENT")
        # Stop all relevant stages individually
        for stage_label in [
            self.const.XY_STAGE_LABEL,
            self.const.Z_PIEZO_LABEL,
            self.const.Z_STAGE_LABEL,
            self.const.FILTER_Z_STAGE_LABEL,
        ]:
            try:
                self.mmc.stop(stage_label)
            except Exception as e:
                print(f"Warn: Could not stop stage '{stage_label}': {e}")

    # --- Utility Methods ---
    def get_pixel_size_um(self) -> float:
        """Returns the camera pixel size from Micro-Manager."""
        try:
            # Use a keyword argument to disambiguate the overloaded method.
            # Ignore the type checker warning, as it struggles with the dynamic
            # nature of pymmcore-plus method overloads.
            return self.mmc.getPixelSizeUm(xyOrZStageLabel=self.const.XY_STAGE_LABEL)  # type: ignore
        except Exception:
            print("Warn: Could not get pixel size. Defaulting to 0.120 µm.")
            return 0.120

    def find_and_set_trigger_mode(self, mode: str) -> bool:
        """Sets the camera trigger mode."""
        if self.is_demo:
            return True
        cam = self.const.CAMERA_A_LABEL
        if not self.mmc.hasProperty(cam, "TriggerMode"):
            return True
        allowed = self.mmc.getAllowedPropertyValues(cam, "TriggerMode")
        if mode in allowed:
            self._set_property(cam, "TriggerMode", mode)
            return True
        print(f"Warn: Mode '{mode}' not supported. Allowed: {allowed}")
        return False
