# src/microscope/hardware/plogic.py
from typing import Callable

from ..config import HW, AcquisitionSettings


class PLogicController:
    """A controller for programming the PLogic card."""

    def __init__(self, execute_serial_command: Callable):
        self._execute_serial_command = execute_serial_command

    def program_for_acquisition(self, settings: AcquisitionSettings):
        """Programs the PLogic card for timed camera and laser pulses."""
        addr = HW.plogic_label[-2:]
        galvo_trigger = HW.plogic_galvo_trigger_ttl_addr
        clock = HW.plogic_4khz_clock_addr
        cam_delay_cell = 12
        laser_delay_cell = 11
        laser_pulse_cell = 10

        self._execute_serial_command(f"{addr}RM F")  # Reset all cell functions
        self._execute_serial_command(f"{addr}RM Z")  # Reset all cell configs

        # Configure camera delay/pulse
        delay = int(settings.delay_before_camera_ms * HW.pulses_per_ms)
        self._execute_serial_command(f"{addr}M E={cam_delay_cell}")
        self._execute_serial_command(f"{addr}CCA Y=13")  # Delay one-shot
        self._execute_serial_command(f"{addr}CCA Z={delay}")
        self._execute_serial_command(f"{addr}CCB X={galvo_trigger} Y={clock}")

        # Configure laser delay
        delay = int(settings.delay_before_laser_ms * HW.pulses_per_ms)
        self._execute_serial_command(f"{addr}M E={laser_delay_cell}")
        self._execute_serial_command(f"{addr}CCA Y=13")
        self._execute_serial_command(f"{addr}CCA Z={delay}")
        self._execute_serial_command(f"{addr}CCB X={galvo_trigger} Y={clock}")

        # Configure laser pulse duration
        duration = int(settings.laser_trig_duration_ms * HW.pulses_per_ms)
        self._execute_serial_command(f"{addr}M E={laser_pulse_cell}")
        self._execute_serial_command(f"{addr}CCA Y=14")  # NRT one-shot
        self._execute_serial_command(f"{addr}CCA Z={duration}")
        self._execute_serial_command(f"{addr}CCB X={128 + laser_delay_cell} Y={clock}")

        # Route cell outputs to physical TTL BNCs
        cam_output_bnc = 44
        laser_output_bnc = 45
        self._execute_serial_command(f"{addr}TTL X={cam_output_bnc} Y=8")
        self._execute_serial_command(f"{addr}TTL X={laser_output_bnc} Y=8")
        self._execute_serial_command(f"{addr}M E={cam_output_bnc}")
        self._execute_serial_command(f"{addr}CCA Y=1")
        self._execute_serial_command(f"{addr}CCB X={cam_delay_cell}")
        self._execute_serial_command(f"{addr}M E={laser_output_bnc}")
        self._execute_serial_command(f"{addr}CCA Y=1")
        self._execute_serial_command(f"{addr}CCB X={laser_pulse_cell}")
