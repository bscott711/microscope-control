import serial

from .base import BaseHardwareController


class PLogicHardwareController(BaseHardwareController):
    """
    Comprehensive hardware controller for the ASI Programmable Logic card.
    Provides low-level primitives for card programming.
    """

    def __init__(self):
        super().__init__()
        self._axis = "E"  # Standard PLogic axis letter

    def set_pointer(self, ser: serial.Serial, plogic_addr: str, position: int):
        """Sets the programming pointer to a specific cell or I/O address."""
        self._send_command(ser, f"{plogic_addr}M {self._axis}={position}")

    def set_cell_type(self, ser: serial.Serial, plogic_addr: str, type_code: int):
        """Sets the type of the logic cell at the current pointer position."""
        self._send_command(ser, f"{plogic_addr}CCA Y={type_code}")

    def set_cell_config(self, ser: serial.Serial, plogic_addr: str, config_value: int):
        """Sets the configuration value of the cell at the current pointer."""
        self._send_command(ser, f"{plogic_addr}CCA Z={config_value}")

    def set_cell_inputs(self, ser: serial.Serial, plogic_addr: str, in1: int, in2: int = 0, in3: int = 0, in4: int = 0):
        """Sets the inputs for the cell at the current pointer."""
        self._send_command(ser, f"{plogic_addr}CCB X={in1} Y={in2} Z={in3} F={in4}")

    def execute_preset(self, ser: serial.Serial, plogic_addr: str, preset_num: int):
        """Executes a built-in card preset."""
        self._send_command(ser, f"{plogic_addr}CCA X={preset_num}")

    def save_settings(self, ser: serial.Serial, plogic_addr: str):
        """Saves the current PLogic configuration to non-volatile memory."""
        self._send_command(ser, f"{plogic_addr}SS Z")

    # --- Convenience method for the Z-stack ---
    def configure_for_triggers(self, ser: serial.Serial, params: dict):
        """High-level method to program the laser/camera triggers for the Z-stack."""
        plogic_addr = params["plogic_card_addr"]
        trigger_addr = 41
        laser_tics = int(params["laser_duration_ms"] / 0.25)
        cam_tics = int(params["camera_exposure_ms"] / 0.25)

        # Program one-shots
        self.set_pointer(ser, plogic_addr, 1)
        self.set_cell_type(ser, plogic_addr, 14)  # One-shot
        self.set_cell_config(ser, plogic_addr, laser_tics)
        self.set_cell_inputs(ser, plogic_addr, trigger_addr + 128, 192)

        self.set_pointer(ser, plogic_addr, 2)
        self.set_cell_type(ser, plogic_addr, 14)  # One-shot
        self.set_cell_config(ser, plogic_addr, cam_tics)
        self.set_cell_inputs(ser, plogic_addr, trigger_addr + 128, 192)

        # Route outputs
        self.set_pointer(ser, plogic_addr, 37)  # BNC5
        self._send_command(ser, f"{plogic_addr}CCA Y=2")  # Push-pull output
        self._send_command(ser, f"{plogic_addr}CCA Z=1")  # Source from cell 1

        self.set_pointer(ser, plogic_addr, 33)  # BNC1
        self._send_command(ser, f"{plogic_addr}CCA Y=2")
        self._send_command(ser, f"{plogic_addr}CCA Z=2")  # Source from cell 2

        self.save_settings(ser, plogic_addr)
