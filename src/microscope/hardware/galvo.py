import serial

from .base import BaseHardwareController


class GalvoHardwareController(BaseHardwareController):
    """Hardware controller for the Galvo scanner card."""

    def __init__(self):
        super().__init__()

    def configure_for_z_stack(self, ser: serial.Serial, params: dict):
        """Configures the galvo card for a hardware-timed Z-stack."""
        galvo_addr = params["galvo_card_addr"]
        galvo_axis = params["galvo_axis"]
        num_slices = params["num_slices"]

        z_step_degrees = params["z_step_um"] / params["microns_per_degree"]
        z_step_millidegrees = z_step_degrees * 1000

        self._send_command(ser, f"{galvo_addr}ZS {galvo_axis}={z_step_millidegrees} Y={num_slices}")
        self._send_command(ser, f"{galvo_addr}TTL X=4")
        self._send_command(ser, f"{galvo_addr}TTL Y=2")
        self._send_command(ser, f"{galvo_addr}RT Y=1")
        self._send_command(ser, f"{galvo_addr}SS Z")
