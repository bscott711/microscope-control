# hardware_control.py
import os
import time
import traceback
from typing import List, Optional

from pymmcore_plus import CMMCorePlus

from .config import AcquisitionSettings, HW

mmc = CMMCorePlus.instance()


def _execute_tiger_serial_command(command_string: str):
    original_setting = mmc.getProperty(
        HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange"
    )
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "No")
    mmc.setProperty(HW.tiger_comm_hub_label, "SerialCommand", command_string)
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "Yes")
    time.sleep(0.02)


def set_property(device_label: str, property_name: str, value):
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(
        device_label, property_name
    ):
        if mmc.getProperty(device_label, property_name) != str(value):
            mmc.setProperty(device_label, property_name, value)
    else:
        print(
            f"Warning: Cannot set '{property_name}' for device '{device_label}'. "
            "Device or property not found."
        )


def configure_plogic_for_one_shot_laser(settings: AcquisitionSettings):
    plogic_addr = HW.plogic_label[-2:]
    _execute_tiger_serial_command(f"{plogic_addr}CCA X={HW.plogic_laser_preset_num}")
    _execute_tiger_serial_command(f"M E={HW.plogic_laser_on_cell}")
    _execute_tiger_serial_command("CCA Y=14")
    pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={pulse_duration_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_camera_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_laser_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )
    _execute_tiger_serial_command(f"M E={HW.plogic_delay_before_camera_cell}")
    _execute_tiger_serial_command("CCA Y=13")
    delay_cycles = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"CCA Z={delay_cycles}")
    _execute_tiger_serial_command(
        f"CCB X={HW.plogic_galvo_trigger_ttl_addr} Y={HW.plogic_4khz_clock_addr}"
    )


def calculate_galvo_parameters(settings: AcquisitionSettings):
    if abs(HW.slice_calibration_slope_um_per_deg) < 1e-9:
        raise ValueError("Slice calibration slope cannot be zero.")
    num_slices_ctrl = settings.num_slices
    piezo_amplitude_um = (num_slices_ctrl - 1) * settings.step_size_um
    if HW.camera_mode_is_overlap:
        if num_slices_ctrl > 1:
            piezo_amplitude_um *= float(num_slices_ctrl) / (num_slices_ctrl - 1.0)
        num_slices_ctrl += 1
    galvo_slice_amplitude_deg = (
        piezo_amplitude_um / HW.slice_calibration_slope_um_per_deg
    )
    galvo_slice_center_deg = (
        settings.piezo_center_um - HW.slice_calibration_offset_um
    ) / HW.slice_calibration_slope_um_per_deg
    return (
        round(galvo_slice_amplitude_deg, 4),
        round(galvo_slice_center_deg, 4),
        num_slices_ctrl,
    )


def configure_devices_for_slice_scan(
    settings: AcquisitionSettings,
    galvo_amplitude_deg: float,
    galvo_center_deg: float,
    num_slices_ctrl: int,
):
    piezo_fixed_pos_um = round(settings.piezo_center_um, 3)
    set_property(HW.galvo_a_label, "BeamEnabled", "Yes")
    configure_plogic_for_one_shot_laser(settings)
    set_property(HW.galvo_a_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
    set_property(HW.galvo_a_label, "SPIMNumRepeats", 1)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
    set_property(
        HW.galvo_a_label,
        "SPIMAlternateDirectionsEnable",
        "Yes" if HW.scan_opposite_directions else "No",
    )
    set_property(HW.galvo_a_label, "SPIMScanDuration(ms)", HW.line_scan_duration_ms)
    set_property(HW.galvo_a_label, "SingleAxisYAmplitude(deg)", galvo_amplitude_deg)
    set_property(HW.galvo_a_label, "SingleAxisYOffset(deg)", galvo_center_deg)
    set_property(HW.galvo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.galvo_a_label, "SPIMNumSides", HW.num_sides)
    set_property(HW.galvo_a_label, "SPIMFirstSide", "A" if HW.first_side_is_a else "B")
    set_property(HW.galvo_a_label, "SPIMPiezoHomeDisable", "No")
    set_property(HW.galvo_a_label, "SPIMInterleaveSidesEnable", "No")
    set_property(HW.galvo_a_label, "SingleAxisXAmplitude(deg)", HW.sheet_width_deg)
    set_property(HW.galvo_a_label, "SingleAxisXOffset(deg)", HW.sheet_offset_deg)
    set_property(HW.piezo_a_label, "SingleAxisAmplitude(um)", 0.0)
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", piezo_fixed_pos_um)
    set_property(HW.piezo_a_label, "SPIMNumSlices", num_slices_ctrl)
    set_property(HW.piezo_a_label, "SPIMState", "Armed")


def trigger_slice_scan_acquisition():
    set_property(HW.galvo_a_label, "SPIMState", "Running")


def _reset_for_next_volume():
    print("Resetting controller state for next volume...")
    set_property(HW.galvo_a_label, "BeamEnabled", "No")
    set_property(HW.galvo_a_label, "SPIMState", "Idle")
    set_property(HW.piezo_a_label, "SPIMState", "Idle")


def final_cleanup(settings: AcquisitionSettings):
    print("Performing final cleanup...")
    _reset_for_next_volume()
    set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)


class HardwareInterface:
    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        print("Initializing HardwareInterface...")
        current_config = mmc.systemConfigurationFile() or ""
        target_config = self.config_path
        if not target_config:
            if HW.tiger_comm_hub_label in mmc.getLoadedDevices():
                print(f"Using existing MMCore config: {current_config}")
                return
            raise FileNotFoundError(
                "HardwareInterface requires a config_path, and no valid ASI "
                "config is loaded."
            )
        if not os.path.isabs(target_config):
            target_config = os.path.abspath(target_config)
        if os.path.normcase(current_config) == os.path.normcase(target_config):
            print(f"Target configuration '{target_config}' is already loaded.")
            return
        print(f"Attempting to load configuration: '{target_config}'")
        try:
            mmc.loadSystemConfiguration(target_config)
            if HW.tiger_comm_hub_label not in mmc.getLoadedDevices():
                raise RuntimeError(
                    "Loaded config does not appear to contain an ASI TigerCommHub."
                )
            print(f"Successfully loaded: {mmc.systemConfigurationFile()}")
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{target_config}': {e}")
            traceback.print_exc()
            raise

    @property
    def camera1(self) -> str:
        return HW.camera_a_label

    def find_and_set_trigger_mode(
        self, camera_label: str, desired_modes: List[str]
    ) -> bool:
        if camera_label not in mmc.getLoadedDevices():
            return False
        trigger_prop = "TriggerMode"
        if not mmc.hasProperty(camera_label, trigger_prop):
            return False
        try:
            allowed = mmc.getAllowedPropertyValues(camera_label, trigger_prop)
            for mode in desired_modes:
                if mode in allowed:
                    set_property(camera_label, trigger_prop, mode)
                    return True
            return False
        except Exception:
            return False