# microscope/hardware_control.py
import os
import time
import traceback
from typing import Any, Optional

from pymmcore_plus import CMMCorePlus

from .config import HW, USE_DEMO_CONFIG, AcquisitionSettings

mmc = CMMCorePlus.instance()


def _execute_tiger_serial_command(command_string: str):
    print(f"SERIAL COMMAND: {command_string}")
    if USE_DEMO_CONFIG:
        return
    if HW.tiger_comm_hub_label not in mmc.getLoadedDevices() or not mmc.hasProperty(
        HW.tiger_comm_hub_label, "SerialCommand"
    ):
        print(
            f"Warning: Cannot send serial commands to '{HW.tiger_comm_hub_label}'. "
            "Device or 'SerialCommand' property not found."
        )
        return
    original_setting = mmc.getProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange")
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "No")
    mmc.setProperty(HW.tiger_comm_hub_label, "SerialCommand", command_string)
    if original_setting == "Yes":
        mmc.setProperty(HW.tiger_comm_hub_label, "OnlySendSerialCommandOnChange", "Yes")
    time.sleep(0.02)


def set_property(device_label: str, property_name: str, value: Any):
    if device_label in mmc.getLoadedDevices() and mmc.hasProperty(device_label, property_name):
        if mmc.getProperty(device_label, property_name) != str(value):
            mmc.setProperty(device_label, property_name, value)
    else:
        if not USE_DEMO_CONFIG:
            print(f"Warning: Cannot set '{property_name}' for device '{device_label}'. Device or property not found.")


def configure_plogic_for_acquisition(settings: AcquisitionSettings):
    """
    Configures the PLogic card using a direct timing model based on a
    single galvo trigger per slice.

    This logic replaces the previous state machine with a more robust
    delay/pulse generation scheme.
    """
    plogic_dev_addr = HW.plogic_label[-2:]  # e.g., "36"
    galvo_trigger = HW.galvo_trigger_addr
    clock = HW.clock_source_addr

    # 1. Reset the PLogic card to a clean state
    # RM F clears all cell functions; RM Z clears all cell configurations.
    _execute_tiger_serial_command(f"{plogic_dev_addr}RM F")
    _execute_tiger_serial_command(f"{plogic_dev_addr}RM Z")

    # 2. Configure the Camera Trigger Pulse
    # The camera trigger is a delayed pulse. The "delay one-shot" (type 13)
    # is perfect for this. It outputs a pulse only after a set delay.
    delay_cycles_cam = int(settings.delay_before_camera_ms * HW.pulses_per_ms)

    # Point to the cell that will generate the camera delay
    _execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.camera_delay_cell}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=13")  # Cell Type: Delay one-shot
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={delay_cycles_cam}")
    # Inputs: Trigger (galvo) and Clock (4kHz internal)
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={galvo_trigger} Y={clock}")

    # 3. Configure the Laser Trigger Pulse
    # The laser needs a pulse of a specific duration *after* a specific delay.
    # This requires two cells: one for the delay, one for the pulse.

    # First, create the laser delay cell (this is unused in your config, so we'll use 11)
    laser_delay_cell = 11
    delay_cycles_laser = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
    _execute_tiger_serial_command(f"{plogic_dev_addr}M E={laser_delay_cell}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=13")  # Delay one-shot
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={delay_cycles_laser}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={galvo_trigger} Y={clock}")

    # Second, create the laser "on" pulse, triggered by the delay cell.
    pulse_duration_cycles = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
    # Point to the cell that generates the final laser pulse
    _execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.laser_on_cell}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=14")  # Cell Type: NRT One-shot
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Z={pulse_duration_cycles}")
    # Inputs: Trigger (rising edge of the laser_delay_cell) and Clock
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={128 + laser_delay_cell} Y={clock}")

    # 4. Route the final cell outputs to the physical TTL BNCs
    # Set the TTL output mode to be controlled by the PLogic card (mode 8)
    _execute_tiger_serial_command(f"TTL X={HW.camera_trigger_addr} Y=8")
    _execute_tiger_serial_command(f"TTL X={HW.laser_trigger_addr} Y=8")

    # Connect the camera delay cell's output to the camera TTL BNC
    _execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.camera_trigger_addr}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=1")  # Buffer
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={HW.camera_delay_cell}")

    # Connect the laser "on" cell's output to the laser TTL BNC
    _execute_tiger_serial_command(f"{plogic_dev_addr}M E={HW.laser_trigger_addr}")
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCA Y=1")  # Buffer
    _execute_tiger_serial_command(f"{plogic_dev_addr}CCB X={HW.laser_on_cell}")

    print("PLogic card configured for acquisition.")


def calculate_galvo_parameters(settings: AcquisitionSettings):
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
    settings: AcquisitionSettings,
    galvo_amplitude_deg: float,
    galvo_center_deg: float,
    num_slices_ctrl: int,
):
    piezo_fixed_pos_um = round(settings.piezo_center_um, 3)
    set_property(HW.galvo_a_label, "BeamEnabled", "Yes")
    configure_plogic_for_acquisition(settings)
    set_property(HW.galvo_a_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
    set_property(HW.galvo_a_label, "SPIMNumRepeats", 1)
    set_property(HW.galvo_a_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
    set_property(
        HW.galvo_a_label,
        "SPIMAlternateDirectionsEnable",
        "Yes" if HW.scan_opposite_directions else "No",
    )
    set_property(HW.galvo_a_label, "SPIMScanDuration(ms)", settings.camera_exposure_ms)
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
    mmc.setFocusDevice(HW.piezo_a_label)
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
        return HW.camera_a_label

    def find_and_set_trigger_mode(self, camera_label: str, desired_modes: list[str]) -> bool:
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
