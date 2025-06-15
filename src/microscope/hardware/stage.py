import time

import serial

from .base import BaseHardwareController


class StageHardwareController(BaseHardwareController):
    """
    Comprehensive hardware controller for XY and Z motor stages.
    """

    def __init__(self):
        super().__init__()

    # --- Movement and Position ---
    def move_absolute(self, ser: serial.Serial, axis: str, position_um: float):
        """Moves a stage axis to an absolute position (in micrometers)."""
        pos_asi_units = position_um * 10
        self._send_command(ser, f"M {axis}={pos_asi_units:.1f}")

    def move_relative(self, ser: serial.Serial, axis: str, distance_um: float):
        """Moves a stage axis by a relative amount (in micrometers)."""
        dist_asi_units = distance_um * 10
        self._send_command(ser, f"R {axis}={dist_asi_units:.1f}")

    def get_position_um(self, ser: serial.Serial, axes: list[str]) -> dict:
        """Gets the current position of one or more axes (in micrometers)."""
        response = self._send_command(ser, f"W {' '.join(axes)}")
        parts = response.split(" ")[1:]
        return {axis: float(pos) / 10.0 for axis, pos in zip(axes, parts)}

    def halt(self, ser: serial.Serial):
        """Stops all motor movement immediately."""
        self._send_command(ser, "HALT")

    def wait_for_device(self, ser: serial.Serial, timeout_s: float = 30.0):
        """Waits for all stage motion to complete."""
        start_time = time.monotonic()
        while time.monotonic() - start_time < timeout_s:
            if "N" in self._send_command(ser, "/"):
                return
            time.sleep(0.1)
        raise TimeoutError("Timed out waiting for stage to finish moving.")

    # --- Motion Parameters ---
    def set_speed(self, ser: serial.Serial, axis: str, speed_mms: float):
        """Sets the maximum speed for an axis (in mm/s)."""
        self._send_command(ser, f"S {axis}={speed_mms:.4f}")

    def get_speed(self, ser: serial.Serial, axis: str) -> float:
        """Gets the maximum speed for an axis (in mm/s)."""
        response = self._send_command(ser, f"S {axis}?")
        return float(response.split("=")[1])

    def set_acceleration(self, ser: serial.Serial, axis: str, accel_ms: int):
        """Sets the ramp time for an axis (in milliseconds)."""
        self._send_command(ser, f"AC {axis}={accel_ms}")

    def set_backlash(self, ser: serial.Serial, axis: str, backlash_mm: float):
        """Sets the backlash compensation for an axis (in mm)."""
        self._send_command(ser, f"B {axis}={backlash_mm:.4f}")

    # --- Coordinate System ---
    def set_origin(self, ser: serial.Serial, axis: str):
        """Sets the current position of an axis as the new origin (0)."""
        self._send_command(ser, f"H {axis}=0")

    def zero_all_axes(self, ser: serial.Serial):
        """Sets the current position of all axes to be the origin."""
        self._send_command(ser, "Z")
