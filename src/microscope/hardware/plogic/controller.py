from __future__ import annotations

from typing import TYPE_CHECKING

from microscope.config import AcquisitionSettings

from .asi_commands import ASIPLogicCommands
from .models import PLogicAddress, PLogicCardModel, PLogicCellType, PLogicIOType

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class PLogicController:
    """
    High-level, object-oriented controller for the ASI PLogic card.
    """

    def __init__(self, device_label: str = "PLogic", mmc: CMMCorePlus | None = None) -> None:

        self._mmc = mmc or CMMCorePlus.instance()
        self.model = PLogicCardModel()
        self._asi = ASIPLogicCommands(device_label, self._mmc)

    def read_from_card(self):
        """Synchronizes the local Python model with the hardware's state."""
        self.model = self._asi.read_model_from_card()
        print("INFO: PLogic model synchronized with hardware state.")

    def commit(self):
        """Writes the current state of the Python model to the hardware."""
        self._asi.commit_model_to_card(self.model)

    def load_preset(self, preset_num: int):
        """Loads a hardware preset and syncs the model."""
        self._asi.load_preset(preset_num)
        self.read_from_card()

    def configure_for_mda(self, settings: AcquisitionSettings):
        """
        Programs the PLogic card for a fully autonomous, galvo-driven MDA.

        This method creates a hardware state machine using the logic cells
        to handle T, C, and Z loops, paced by the galvo's line clock.
        """
        print("INFO: Programming PLogic for fully autonomous hardware-timed MDA...")

        # --- Define Hardware Connections ---
        # These would typically come from a persistent config file.
        GALVO_LINE_CLOCK_SOURCE = PLogicAddress.TTL_5_IN
        MASTER_START_TRIGGER = PLogicAddress.BNC_1_IN

        CAMERA_TRIGGER_BNC_NUM = 2
        LASER_1_BNC_NUM, LASER_2_BNC_NUM = 4, 5  # Example for 2 channels

        # --- Clear Model to a Blank State ---
        self.model = PLogicCardModel()

        # --- Cell Assignments & Logic Definition ---
        # This state machine uses a chain of counters. The "done" pulse from
        # one counter serves as the "clock" for the next counter in the chain.

        # Cell 0: Master Latch - A flip-flop that starts/stops the entire sequence.
        master_latch = self.model.cells[0]
        master_latch.cell_type = PLogicCellType.R_S_FLIP_FLOP
        master_latch.inputs[0] = MASTER_START_TRIGGER  # SET input
        # The RESET input will be the "done" signal from the final counter (Timepoints).

        # Cell 1: Channel Counter - Increments on every galvo line clock.
        channel_counter = self.model.cells[1]
        channel_counter.cell_type = PLogicCellType.COUNTER
        channel_counter.config_value = len(settings.channels)
        channel_counter.inputs[0] = GALVO_LINE_CLOCK_SOURCE  # Clock input
        channel_counter.inputs[1] = PLogicAddress.CELL_1_OUT  # Enable input (from master latch)

        # Cell 2: Z-Stack Counter - Increments when the channel counter finishes a cycle.
        z_counter = self.model.cells[2]
        z_counter.cell_type = PLogicCellType.COUNTER
        z_counter.config_value = settings.z_stack.steps if settings.z_stack else 1
        # The clock is the "done" pulse from the channel counter (not directly available,
        # requires another cell to create the pulse, e.g., cell 15).
        z_counter.inputs[0] = PLogicAddress.CELL_15_OUT  # Clock input
        z_counter.inputs[1] = PLogicAddress.CELL_1_OUT  # Enable input

        # Cell 3: Timepoint Counter - Increments when the Z-counter finishes a cycle.
        t_counter = self.model.cells[3]
        t_counter.cell_type = PLogicCellType.COUNTER
        t_counter.config_value = settings.num_timepoints
        # Clocked by the "done" pulse of the Z-counter.
        t_counter.inputs[0] = PLogicAddress.CELL_14_OUT  # Example pulse generator
        t_counter.inputs[1] = PLogicAddress.CELL_1_OUT  # Enable input

        # Connect the final "done" signal from the timepoint counter back to reset the master latch.
        master_latch.inputs[1] = PLogicAddress.CELL_4_OUT  # RESET input

        # Cell 4-7: Laser Selection Logic
        # This logic uses the state of the channel counter to select which laser fires.
        # For simplicity, we'll show logic for two lasers.
        laser_1_logic = self.model.cells[4]  # Logic for laser 1
        laser_1_logic.cell_type = PLogicCellType.AND
        laser_1_logic.inputs[0] = GALVO_LINE_CLOCK_SOURCE  # Trigger with galvo
        # Enable only when channel counter is at a specific state (e.g., 0 for channel 1)
        # This requires more cells to decode the counter state. We'll use a placeholder address for clarity.
        laser_1_logic.inputs[1] = PLogicAddress.CELL_2_OUT  # Placeholder for "channel==0" signal

        laser_2_logic = self.model.cells[5]  # Logic for laser 2
        laser_2_logic.cell_type = PLogicCellType.AND
        laser_2_logic.inputs[0] = GALVO_LINE_CLOCK_SOURCE  # Trigger with galvo
        laser_2_logic.inputs[1] = PLogicAddress.CELL_3_OUT  # Placeholder for "channel==1" signal

        # Cell 8: Camera Trigger Pulse Generation
        # A one-shot cell creates a clean TTL pulse of a defined width for the camera.
        cam_trigger = self.model.cells[8]
        cam_trigger.cell_type = PLogicCellType.ONE_SHOT
        cam_trigger.config_value = 10  # Corresponds to exposure time
        cam_trigger.inputs[0] = GALVO_LINE_CLOCK_SOURCE  # Triggered by galvo line clock

        # --- I/O Routing ---
        # Route the logic cell outputs to the physical BNC ports.

        # Camera Trigger Output
        cam_port = self.model.bnc_ports[CAMERA_TRIGGER_BNC_NUM - 1]
        cam_port.direction = PLogicIOType.OUTPUT_PUSH_PULL
        cam_port.output_source = PLogicAddress.CELL_9_OUT  # Output from Cell 8

        # Laser 1 Output
        laser_1_port = self.model.bnc_ports[LASER_1_BNC_NUM - 1]
        laser_1_port.direction = PLogicIOType.OUTPUT_PUSH_PULL
        laser_1_port.output_source = PLogicAddress.CELL_5_OUT  # Output from laser 1 logic

        # Laser 2 Output
        laser_2_port = self.model.bnc_ports[LASER_2_BNC_NUM - 1]
        laser_2_port.direction = PLogicIOType.OUTPUT_PUSH_PULL
        laser_2_port.output_source = PLogicAddress.CELL_6_OUT  # Output from laser 2 logic

        # --- Commit the full configuration to the card ---
        self.commit()
