import serial

from .base import BaseHardwareController


class CRISPHardwareController(BaseHardwareController):
    """Comprehensive hardware controller for the CRISP autofocus system."""

    def __init__(self):
        super().__init__()

    def lock(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}LK")

    def unlock(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}UL")

    def get_state(self, ser: serial.Serial, crisp_addr: str) -> dict:
        response = self._send_command(ser, f"{crisp_addr}LK?")
        parts = response.split(" ")[-1].split(",")
        state_char = parts[0]
        state_map = {"R": "Ready", "L": "Locked", "F": "In Focus", "E": "Error"}
        return {
            "lock_state": state_map.get(state_char, f"Unknown ({state_char})"),
            "error_number": int(parts[1]) if len(parts) > 1 else 0,
        }

    def calibrate_log_amp(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}CAL R=1")

    def calibrate_dither(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}CAL R=2")

    def set_gain_and_calibrate(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}CAL R=3")

    def set_gain(self, ser: serial.Serial, crisp_addr: str, gain: int):
        if not 1 <= gain <= 10:
            raise ValueError("Gain must be between 1 and 10.")
        self._send_command(ser, f"{crisp_addr}GA X={gain}")

    def set_loop_parameters(self, ser: serial.Serial, crisp_addr: str, p: int, i: int):
        self._send_command(ser, f"{crisp_addr}LP X={p} Y={i}")

    def get_loop_parameters(self, ser: serial.Serial, crisp_addr: str) -> dict:
        response = self._send_command(ser, f"{crisp_addr}LP X? Y?")
        parts = response.split(" ")[1:]
        params = {p.split("=")[0]: int(p.split("=")[1]) for p in parts}
        return {"P": params.get("X"), "I": params.get("Y")}

    def reset_focus_offset(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}LR Y=2")

    def get_snr(self, ser: serial.Serial, crisp_addr: str) -> float:
        response = self._send_command(ser, f"{crisp_addr}SN?")
        return float(response.split(" ")[-1])

    def get_sum(self, ser: serial.Serial, crisp_addr: str) -> int:
        response = self._send_command(ser, f"{crisp_addr}SUM?")
        return int(response.split(" ")[-1])

    def save_calibration(self, ser: serial.Serial, crisp_addr: str):
        self._send_command(ser, f"{crisp_addr}SS Z")
