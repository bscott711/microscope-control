# src/microscope/hardware.py
"""
Hardware Controller Module

This module orchestrates complex, multi-step hardware sequences that are
specific to this application's acquisition strategy. It uses pymmcore-plus
for the underlying device communication.
"""

import time

from pymmcore_plus import CMMCorePlus

from .settings import AcquisitionSettings, HardwareConstants


class HardwareController:
    """A class to orchestrate complex hardware sequences."""

    def __init__(self, mmc: CMMCorePlus, const: HardwareConstants, is_demo: bool = False):
        """
        Initializes the HardwareController.
        Args:
            mmc: The pymmcore-plus instance.
            const: The HardwareConstants data object.
            is_demo: A flag indicating if the system is in demo mode.
        """
        self.mmc = mmc
        self.const = const
        self.is_demo = is_demo
        self.initial_galvo_y_offset: float = 0.0

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
        print(f"[SERIAL] Sending: {command}")

        if original_setting == "Yes":
            self.mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")
        time.sleep(0.02)

    def _set_property(self, device_label: str, prop: str, value):
        """Safely sets a property on a device if it has changed."""
        if self.mmc.hasProperty(device_label, prop):
            if self.mmc.getProperty(device_label, prop) != str(value):
                print(f"Setting {device_label}.{prop} = {value}")
                self.mmc.setProperty(device_label, prop, value)
        else:
            if not self.is_demo:
                print(f"Warn: Property '{prop}' not found on device '{device_label}'.")

    def setup_for_acquisition(self, settings: AcquisitionSettings):
        """Configures all devices for a triggered Z-stack acquisition."""
        print("Configuring devices for acquisition...")
        self.mmc.setCameraDevice(self.const.CAMERA_A_LABEL)
        self.mmc.setExposure(settings.camera_exposure_ms)
        self._set_property(self.const.CAMERA_A_LABEL, "TriggerMode", "Edge Trigger")
        self._configure_plogic(settings)
        self._configure_spim_scan(settings)
        self._arm_spim_devices()

    def _configure_plogic(self, settings: AcquisitionSettings):
        """Programs the PLogic card with the application-specific timing."""
        self._reset_plogic()
        plogic_addr = self.const.PLOGIC_LABEL[-2:]
        print(f"Programming PLogic at {plogic_addr}")
        # ... (PLogic commands as before)
        self._execute_tiger_serial_command(f"{plogic_addr}CCA X={self.const.PLOGIC_LASER_PRESET_NUM}")
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_LASER_ON_CELL}")
        self._execute_tiger_serial_command("CCA Y=14")
        cycles = int(settings.laser_trig_duration_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR} Y={self.const.PLOGIC_4KHZ_CLOCK_ADDR}"
        )
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_DELAY_BEFORE_LASER_CELL}")
        self._execute_tiger_serial_command("CCA Y=13")
        cycles = int(settings.delay_before_laser_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={self.const.PLOGIC_4KHZ_CLOCK_ADDR}"
        )
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_DELAY_BEFORE_CAMERA_CELL}")
        self._execute_tiger_serial_command("CCA Y=13")
        cycles = int(settings.delay_before_camera_ms * self.const.PULSES_PER_MS)
        self._execute_tiger_serial_command(f"CCA Z={cycles}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_GALVO_TRIGGER_TTL_ADDR} Y={self.const.PLOGIC_4KHZ_CLOCK_ADDR}"
        )
        self._execute_tiger_serial_command(f"M E={self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR}")
        self._execute_tiger_serial_command(
            f"CCB X={self.const.PLOGIC_DELAY_BEFORE_CAMERA_CELL} Y={self.const.PLOGIC_4KHZ_CLOCK_ADDR}"
        )
        self._execute_tiger_serial_command(f"{plogic_addr}M D={self.const.PLOGIC_4KHZ_CLOCK_ADDR}")
        self._execute_tiger_serial_command(f"{plogic_addr}M E={self.const.PLOGIC_CAMERA_TRIGGER_TTL_ADDR}")

    def _configure_spim_scan(self, settings: AcquisitionSettings):
        """Sets all SPIM properties on the Tiger controller."""
        galvo = self.const.GALVO_A_LABEL
        piezo = self.const.Z_PIEZO_LABEL
        slope = self.const.SLICE_CALIBRATION_SLOPE_UM_PER_DEG
        try:
            self.initial_galvo_y_offset = self.mmc.getYPosition(galvo)
        except Exception:
            self.initial_galvo_y_offset = 0.0  # Demo mode case

        num_slices_ctrl = settings.num_slices
        piezo_travel_um = (settings.num_slices - 1) * settings.step_size_um
        galvo_amplitude_deg = piezo_travel_um / slope if slope else 0

        self._set_property(galvo, "SPIMNumSlices", num_slices_ctrl)
        self._set_property(galvo, "SingleAxisYAmplitude(deg)", round(galvo_amplitude_deg, 4))
        self._set_property(galvo, "SingleAxisYOffset(deg)", round(self.initial_galvo_y_offset, 4))
        self._set_property(piezo, "SingleAxisOffset(um)", settings.piezo_center_um)
        self._set_property(galvo, "SPIMNumSlicesPerPiezo", self.const.LINE_SCANS_PER_SLICE)
        self._set_property(galvo, "SPIMScanDuration(ms)", self.const.LINE_SCAN_DURATION_MS)
        self._set_property(piezo, "SPIMNumSlices", num_slices_ctrl)

    def _arm_spim_devices(self):
        """Sets the SPIM state of relevant devices to 'Armed'."""
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Armed")
        self._set_property(self.const.Z_PIEZO_LABEL, "SPIMState", "Armed")

    def _reset_plogic(self):
        """Sends the PLogic reset command."""
        plogic_addr = self.const.PLOGIC_LABEL[-2:]
        print("[DEBUG] Resetting PLogic...")
        self._execute_tiger_serial_command(f"{plogic_addr}M R")

    def trigger_acquisition(self):
        """Sends the master trigger to start the armed SPIM sequence."""
        print("Triggering acquisition...")
        self._set_property(self.const.GALVO_A_LABEL, "SPIMState", "Running")

    def final_cleanup(self, settings: AcquisitionSettings):
        """Resets hardware to a safe, idle state after acquisition."""
        print("Performing final hardware cleanup...")
        galvo = self.const.GALVO_A_LABEL
        self._set_property(galvo, "SPIMState", "Idle")
        self._set_property(self.const.Z_PIEZO_LABEL, "SPIMState", "Idle")
        self._set_property(galvo, "SingleAxisYOffset(deg)", self.initial_galvo_y_offset)
        self._set_property(self.const.Z_PIEZO_LABEL, "SingleAxisOffset(um)", settings.piezo_center_um)
        self._set_property(self.const.CAMERA_A_LABEL, "TriggerMode", "Internal Trigger")
