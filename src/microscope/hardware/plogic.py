# src/microscope/hardware/plogic.py
from typing import Callable

from ..config import HW, AcquisitionSettings


class PLogicController:
    """
    A controller for programming the PLogic card based on the validated
    log file sequence.
    """

    def __init__(self, execute_serial_command: Callable):
        """
        Initializes the PLogicController.

        Args:
            execute_serial_command: A function that can send a raw serial
                                    command string to the Tiger controller.
        """
        self._execute = execute_serial_command
        self.addr = HW.plogic_label[-2:]

    def program_for_acquisition(self, settings: AcquisitionSettings):
        """
        Programs the PLogic card by replicating the source-of-truth log sequence.
        """
        print("Programming PLogic card with validated sequence...")

        # --- Program Logic Cell #6 ---
        self._execute(f"{self.addr}M E=6")  # Move Pointer to cell 6
        self._execute(f"{self.addr}CCA Y=14")  # Set cell type to one-shot
        self._execute(f"{self.addr}CCA Z=10")  # Set config
        self._execute(f"{self.addr}CCB X=169")  # Set input 1
        self._execute(f"{self.addr}CCB Y=233")  # Set input 2
        self._execute(f"{self.addr}CCB Z=129")  # Set input 3

        # --- Program Logic Cell #7 ---
        self._execute(f"{self.addr}M E=7")  # Move Pointer to cell 7
        self._execute(f"{self.addr}CCA Y=14")  # Set cell type to one-shot
        self._execute(f"{self.addr}CCA Z=1")  # Set config
        self._execute(f"{self.addr}CCB X=134")  # Set input 1
        self._execute(f"{self.addr}CCB Y=198")  # Set input 2
        self._execute(f"{self.addr}CCB Z=129")  # Set input 3

        # --- Arm the logic circuit ---
        self._execute(f"{self.addr}CCA X=3")  # "cell 1 high" preset

        # --- Set final preset for trigger routing ---
        self._execute(f"{self.addr}CCA X=11")

    def cleanup(self):
        """Sets the PLogic card to a safe, idle state after acquisition."""
        self._execute(f"{self.addr}CCA X=10")  # "cell 8 low" preset
