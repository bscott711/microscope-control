from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pymmcore_plus import CMMCorePlus

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASITigerStageCommands:
    """
    LOW-LEVEL: Provides a complete, Pythonic interface for all custom
    ASI Tiger stage commands, including tuning, limits, and advanced modules.
    """

    def __init__(
        self,
        tiger_hub_label: str,
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or CMMCorePlus.instance()
        self._hub = tiger_hub_label

    def _send(self, command: str) -> str:
        """Send a command to the Tiger hub and get the response."""
        self._mmc.setProperty(self._hub, "SerialCommand", command)
        response = self._mmc.getProperty(self._hub, "SerialResponse")
        if ":N" in response:
            raise RuntimeError(f"ASI command failed: '{command}' -> {response}")
        return response

    def _get_axis_value(self, command: str, axis: str) -> str:
        """Query an axis-specific value and parse it."""
        response = self._send(f"{command} {axis}?")
        # Expected format is ":A [value]"
        return response.split(" ")[-1].strip()

    # --- Motion Tuning ---

    def set_backlash(self, axis: str, distance_mm: float):
        """Sets the anti-backlash move distance (BACKLASH command)."""
        self._send(f"B {axis}={distance_mm}")

    def set_overshoot(self, axis: str, distance_mm: float):
        """Sets the move overshoot distance (OVERSHOOT command)."""
        self._send(f"OS {axis}={distance_mm}")

    def set_joystick_speed(self, fast_percent: float, slow_percent: float):
        """Sets the joystick fast and slow speeds (JSSPD command)."""
        self._send(f"JSSPD F={fast_percent} S={slow_percent}")

    def set_maintain_power_mode(self, axis: str, mode: Literal[0, 1, 2, 3]):
        """Sets servo power behavior after a move (MAINTAIN command)."""
        self._send(f"MA {axis}={mode}")

    # --- Position and Limits ---

    def set_current_position_as_zero(self, axis: str):
        """Define the current position as the new zero (ZERO command)."""
        self._send(f"Z {axis}")

    def set_travel_limits(self, axis: str, low_mm: float, high_mm: float):
        """Set the software travel limits (SETLOW/SETHIGH commands)."""
        self._send(f"SL {axis}={low_mm}")
        self._send(f"SH {axis}={high_mm}")

    # --- Ring Buffer (Saved Positions) ---

    def clear_ring_buffer(self):
        self._send("RM X=0")

    def load_ring_buffer_position(self, **kwargs: float):
        pos_str = " ".join([f"{ax}={pos * 10}" for ax, pos in kwargs.items()])
        self._send(f"LD {pos_str}")

    def enable_ring_buffer_ttl(self, mode: Literal[1, 2, 3]):
        """Sets the TTL trigger mode for the ring buffer (RBMODE command)."""
        self._send(f"RM T={mode}")

    def set_ring_buffer_speed(self, speed_mms: float):
        """Sets the speed for ring buffer moves (RBSPEED command)."""
        self._send(f"RBSPEED F={speed_mms}")

    # --- Hardware Z-Stack ---

    def setup_z_stack(self, z_step_um: float, num_slices: int):
        z_step_tenths = z_step_um * 10
        self._send(f"ZS A={z_step_tenths} Y={num_slices}")

    def start_z_stack(self):
        self._send("ZS S=1")

    def stop_z_stack(self):
        self._send("ZS S=0")
