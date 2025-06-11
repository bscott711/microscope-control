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
            current_value = self.mmc.getProperty(device_label, prop)
            if current_value != str(value):
                print(f"Setting {device_label}.{prop} = {value} (was {current_value})")
                self.mmc.setProperty(device_label, prop, value)
        else:
            print(f"Warn: Property '{prop}' not found on device '{device_label}'.")

    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Configures all devices for a triggered Z-stack acquisition."""
        print("Configuring devices for acquisition...")
        self.mmc.setCameraDevice(self.const.CAMERA_A_LABEL)
        self.mmc.setExposure(settings.camera_exposure_ms)

        # Set Trigger Mode
        if not self.find_and_set_trigger_mode("Edge Trigger"):
            raise RuntimeError("Failed to set external trigger mode.")

        # Configure PLogic timing
        self._configure_plogic(settings)

        # Configure SPIM scan parameters
        self._configure_spim_scan(settings)

        # Arm SPIM devices
        self._arm_spim_devices()

    def _configure_plogic(self, settings: AcquisitionSettings):
        """Programs the PLogic card for timed laser and camera pulses."""
        plogic_addr = self.const.PLOGIC_LABEL[-2:]
        print(f"Programming PLogic at {plogic_addr}")

        self._execute_tiger_serial_command(
            f"{plogic_addr}CCA X={self.const.PLOGIC_LASER_PRESET_NUM}"
        )
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_LASER_ON_CELL}")
        self._execute_tiger_serial_command("CCA Y=14")
        cycles = int(settings.laser_trig_duration_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")
        cam_ttl = self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR
        clock_addr = self.const.PLOGIC_4KHZ_CLOCK_ADDR
        cmd = f"CCB X={cam_ttl} Y={clock_addr}"
        self._execute_tiger_serial_command(cmd)

        # Optional: Delay before laser
        delay_cycles = int(settings.delay_before_laser_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command("CCA Y=13")
        self._execute_tiger_serial_command(f"CCA Z={delay_cycles}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={clock_addr}"
        )

        # Optional: Delay before camera
        delay_cycles = int(settings.delay_before_camera_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command("CCA Y=13")
        self._execute_tiger_serial_command(f"CCA Z={delay_cycles}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={clock_addr}"
        )

    def _configure_spim_scan(self, settings: AcquisitionSettings):
        """Sets all SPIM properties on the Tiger controller."""
        galvo = self.const.GALVO_A_LABEL
        piezo = self.const.Z_PIEZO_LABEL
        slope = self.const.SLICE_CALIBRATION_SLOPE_UM_PER_DEG

        if abs(slope) < 1e-9:
            raise ValueError("Slice calibration slope cannot be zero.")

        try:
            current_offset_deg_str = self.mmc.getProperty(
                galvo, "SingleAxisYOffset(deg)"
            )
            self.initial_galvo_y_offset = float(current_offset_deg_str)
        except Exception:
            print("Warn: Could not get galvo offset. Defaulting to 0.")
            self.initial_galvo_y_offset = 0.0

        num_slices_ctrl = settings.num_slices
        if self.const.CAMERA_MODE_IS_OVERLAP:
            if num_slices_ctrl > 1:
                num_slices_ctrl += 1

        piezo_travel_um = (settings.num_slices - 1) * settings.step_size_um
        galvo_amplitude_deg = piezo_travel_um / slope

        # Galvo Setup
        self._set_property(galvo, "SPIMNumSlices", num_slices_ctrl)
        self._set_property(
            galvo, "SingleAxisYAmplitude(deg)", round(galvo_amplitude_deg, 4)
        )
        self._set_property(
            galvo, "SingleAxisYOffset(deg)", round(self.initial_galvo_y_offset, 4)
        )
        self._set_property(
            galvo, "SPIMNumSlicesPerPiezo", self.const.LINE_SCANS_PER_SLICE
        )
        self._set_property(
            galvo, "SPIMDelayBeforeRepeat(ms)", self.const.DELAY_BEFORE_SCAN_MS
        )
        self._set_property(galvo, "SPIMNumRepeats", 1)
        self._set_property(
            galvo, "SPIMDelayBeforeSide(ms)", self.const.DELAY_BEFORE_SIDE_MS
        )
        self._set_property(
            galvo,
            "SPIMAlternateDirectionsEnable",
            "Yes" if self.const.SCAN_OPPOSITE_DIRECTIONS else "No",
        )
        self._set_property(
            galvo, "SPIMScanDuration(ms)", self.const.LINE_SCAN_DURATION_MS
        )
        self._set_property(galvo, "SPIMNumSides", self.const.NUM_SIDES)
        self._set_property(
            galvo, "SPIMFirstSide", "A" if self.const.FIRST_SIDE_IS_A else "B"
        )
        self._set_property(galvo, "SPIMPiezoHomeDisable", "No")
        self._set_property(galvo, "SPIMInterleaveSidesEnable", "No")
        self._set_property(
            galvo, "SingleAxisXAmplitude(deg)", self.const.SHEET_WIDTH_DEG
        )
        self._set_property(galvo, "SingleAxisXOffset(deg)", self.const.SHEET_OFFSET_DEG)

        # Piezo Setup
        self._set_property(piezo, "SingleAxisAmplitude(um)", 0.0)
        self._set_property(piezo, "SingleAxisOffset(um)", settings.piezo_center_um)
        self._set_property(piezo, "SPIMNumSlices", num_slices_ctrl)

    def _arm_spim_devices(self):
        """Sets the SPIM state of relevant devices to 'Armed'."""
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Armed")
        self._set_property(self.const.Z_PIEZO_LABEL, "SPIMState", "Armed")

    def trigger_acquisition(self):
        """Sends the master trigger to start the armed sequence."""
        print("Triggering acquisition...")
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Running")

    def final_cleanup(self, settings: AcquisitionSettings):
        """Resets hardware to a safe, idle state after acquisition."""
        print("Performing final hardware cleanup...")
        galvo = self.const.GALVO_A_LABEL
        self._set_property(galvo, "BeamEnabled", "No")
        self._set_property(galvo, "SPIMState", "Idle")
        self._set_property(self.const.Z_PIEZO_LABEL, "SPIMState", "Idle")
        self._set_property(galvo, "SingleAxisYOffset(deg)", self.initial_galvo_y_offset)
        self._set_property(
            self.const.Z_PIEZO_LABEL, "SingleAxisOffset(um)", settings.piezo_center_um
        )
        self.find_and_set_trigger_mode("Internal Trigger")

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
        """Moves a 1D stage to an absolute position."""
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

    def start_jog(self, device_label: str, speed_microns_per_sec: float):
        """Starts jogging a stage continuously."""
        print(f"Jogging {device_label} at {speed_microns_per_sec} µm/s")
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

    def get_pixel_size_um(self) -> float:
        """Returns the camera pixel size from Micro-Manager."""
        try:
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
            return False

        allowed = self.mmc.getAllowedPropertyValues(cam, "TriggerMode")
        if mode in allowed:
            self._set_property(cam, "TriggerMode", mode)
            return True

        print(f"Warn: Mode '{mode}' not supported. Allowed: {allowed}")
        return False
