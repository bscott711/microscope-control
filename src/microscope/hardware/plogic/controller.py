# hardware/plogic/controller.py
from __future__ import annotations

from typing import TYPE_CHECKING

# This import path needs to be correct in your project structure
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
        self._asi = ASIPLogicCommands(self._mmc, device_label)

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
        GALVO_LINE_CLOCK_SOURCE = PLogicAddress.TTL_5_IN
        MASTER_START_TRIGGER = PLogicAddress.BNC_1_IN
        CAMERA_TRIGGER_BNC_NUM = 2
        LASER_1_BNC_NUM = 4

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

        # Cell 1: Channel Counter has been removed as `settings.channels` no longer exists.
        # If you need to re-implement channel control, you would do so here.
        # For now, we connect the Z-Counter clock directly to the galvo line clock.
        channel_counter_done_signal = GALVO_LINE_CLOCK_SOURCE

        # Cell 2: Z-Stack Counter - Increments when the channel counter finishes
        z_counter = self.model.cells[1]  # Using cell 1 now
        z_counter.cell_type = PLogicCellType.COUNTER
        z_counter.config_value = settings.num_slices
        z_counter.inputs[0] = channel_counter_done_signal  # Clock input
        z_counter.inputs[1] = PLogicAddress.CELL_1_OUT  # Master latch

        # Cell 3: Timepoint Counter - Increments when the Z-counter finishes a cycle.
        t_counter = self.model.cells[2]  # Using cell 2 now
        t_counter.cell_type = PLogicCellType.COUNTER
        t_counter.config_value = settings.time_points
        t_counter.inputs[0] = PLogicAddress.CELL_2_OUT  # Z-counter "done" signal
        t_counter.inputs[1] = PLogicAddress.CELL_1_OUT  # Master latch

        # Connect the final "done" signal back to reset the master latch.
        master_latch.inputs[1] = PLogicAddress.CELL_3_OUT  # t_counter "done"

        # Cell 8: Camera Trigger Pulse Generation
        cam_trigger = self.model.cells[8]
        cam_trigger.cell_type = PLogicCellType.ONE_SHOT
        cam_trigger.config_value = 10  # 10 * 0.25ms = 2.5ms pulse
        cam_trigger.inputs[0] = GALVO_LINE_CLOCK_SOURCE

        # --- I/O Routing ---
        cam_port = self.model.bnc_ports[CAMERA_TRIGGER_BNC_NUM - 1]
        cam_port.direction = PLogicIOType.OUTPUT_PUSH_PULL
        cam_port.output_source = PLogicAddress.CELL_9_OUT

        laser_1_port = self.model.bnc_ports[LASER_1_BNC_NUM - 1]
        laser_1_port.direction = PLogicIOType.OUTPUT_PUSH_PULL
        # Directly gate the laser with the master latch for now
        laser_1_port.output_source = PLogicAddress.CELL_1_OUT

        # --- Commit the full configuration to the card ---
        self.commit()
