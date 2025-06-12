# microscope/hardware_control.py
import os
import time
import traceback
from typing import List, Optional

from .config import AcquisitionSettings, HW, USE_DEMO_CONFIG
from pymmcore_plus import CMMCorePlus

mmc = CMMCorePlus.instance()


def _execute_tiger_serial_command(command_string: str):
    """
    Executes a serial command on the TigerCommHub.

    In demo mode, it will simply print the command instead of executing it.
    """
    if USE_DEMO_CONFIG:
        print(f"DEMO MODE: Skipping serial command: {command_string}")
        return

    if HW.tiger_comm_hub_label not in mmc.getLoadedDevices() or not mmc.hasProperty(
        HW.tiger_comm_hub_label, "SerialCommand"
    ):
        print(
            f"Warning: Cannot send serial commands to '{HW.tiger_comm_hub_label}'. "
            "Device or 'SerialCommand' property not found."
        )
        return

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
        if not USE_DEMO_CONFIG:
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


def _load_demo_config():
    """Programmatically load a demo configuration."""
    print("Programmatically loading DEMO configuration...")
    mmc.loadDevice(HW.camera_a_label, "DemoCamera", "DCam")
    mmc.loadDevice(HW.piezo_a_label, "DemoCamera", "DStage")
    mmc.loadDevice(HW.galvo_a_label, "DemoCamera", "DXYStage")
    mmc.loadDevice(HW.tiger_comm_hub_label, "DemoCamera", "DShutter")
    mmc.loadDevice(HW.plogic_label, "DemoCamera", "DShutter")
    mmc.initializeAllDevices()

    # CORRECTED: A pixel size "configuration" must be defined before setting
    # the pixel size. The name of this configuration is then used to set the value.
    # We will create a configuration named "px" as was done in the .cfg file.
    mmc.definePixelSizeConfig("px")
    mmc.setPixelSizeUm("px", 1.0)


class HardwareInterface:
    def __init__(self, config_file_path: Optional[str] = None):
        self.config_path: Optional[str] = config_file_path
        self._initialize_hardware()

    def _initialize_hardware(self):
        print("Initializing HardwareInterface...")

        if USE_DEMO_CONFIG:
            try:
                _load_demo_config()
                return
            except Exception as e:
                print(f"CRITICAL Error loading DEMO configuration: {e}")
                traceback.print_exc()
                raise

        if not self.config_path or not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"Hardware config file not found at '{self.config_path}'"
            )

        print(f"Attempting to load configuration: '{self.config_path}'")
        try:
            mmc.loadSystemConfiguration(self.config_path)
        except Exception as e:
            print(f"CRITICAL Error loading configuration '{self.config_path}': {e}")
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