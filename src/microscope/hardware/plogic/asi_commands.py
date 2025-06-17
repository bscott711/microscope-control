# hardware/plogic/asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ..common import BaseASICommands
from .models import PLogicCardModel

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPLogicCommands(BaseASICommands):
    """LOW-LEVEL: Translates a PLogicCardModel into ASI serial commands."""

    _ADDR_MAP: ClassVar[dict[str, tuple[int, int]]] = {
        **{f"CELL_TYPE_{i}": (101, i) for i in range(1, 17)},
        **{f"CELL_CONFIG_{i}": (102, i) for i in range(1, 17)},
        **{f"CELL_INPUT_{i}_{j}": (102 + j, i) for i in range(1, 17) for j in range(1, 5)},
        **{f"BNC_DIRECTION_{i}": (131, i) for i in range(1, 9)},
        **{f"BNC_OUTPUT_SOURCE_{i}": (132, i) for i in range(1, 9)},
        **{f"TTL_DIRECTION_{i}": (133, i) for i in range(1, 9)},
        **{f"TTL_OUTPUT_SOURCE_{i}": (134, i) for i in range(1, 9)},
    }

    def __init__(self, mmc: CMMCorePlus, command_device_label: str = "PLogic") -> None:
        super().__init__(mmc, command_device_label)
        self._port = self._mmc.getProperty(self._command_device, "Port")

    def _send(self, command: str) -> str:
        """Sends a command to the PLogic device."""
        full_command = f"{self._command_device} {command}"
        self._mmc.setSerialPortCommand(self._port, full_command, "\r")
        return self._mmc.getSerialPortAnswer(self._port, "\r")

    def _set_address(self, addr_x: int, addr_y: int = 0):
        self._send(f"M X={addr_x} Y={addr_y}")

    def _write_value(self, val_a: int = 0, val_b: int = 0):
        self._send(f"CCA Y={val_a} F={val_b}")

    def commit_model_to_card(self, model: PLogicCardModel):
        """Programs the physical card to match the state of the provided model."""
        # Program all 16 logic cells
        for i, cell in enumerate(model.cells):
            cell_idx = i + 1
            self._set_address(*self._ADDR_MAP[f"CELL_TYPE_{cell_idx}"])
            self._write_value(cell.cell_type.value)
            self._set_address(*self._ADDR_MAP[f"CELL_CONFIG_{cell_idx}"])
            self._write_value(cell.config_value)
            for j, input_addr in enumerate(cell.inputs):
                self._set_address(*self._ADDR_MAP[f"CELL_INPUT_{cell_idx}_{j + 1}"])
                self._write_value(input_addr.value)

        # Program all 8 BNC ports
        for i, port in enumerate(model.bnc_ports):
            bnc_idx = i + 1
            self._set_address(*self._ADDR_MAP[f"BNC_DIRECTION_{bnc_idx}"])
            self._write_value(port.direction.value)
            self._set_address(*self._ADDR_MAP[f"BNC_OUTPUT_SOURCE_{bnc_idx}"])
            self._write_value(port.output_source.value)

        # Program all 8 TTL ports
        for i, port in enumerate(model.ttl_ports):
            ttl_idx = i + 1
            self._set_address(*self._ADDR_MAP[f"TTL_DIRECTION_{ttl_idx}"])
            self._write_value(port.direction.value)
            self._set_address(*self._ADDR_MAP[f"TTL_OUTPUT_SOURCE_{ttl_idx}"])
            self._write_value(port.output_source.value)

    def read_model_from_card(self) -> PLogicCardModel:
        """Reads the current state of the hardware into a PLogicCardModel."""
        # This is a placeholder for the implementation that reads from the hardware
        raise NotImplementedError("Reading from PLogic card is not yet implemented.")

    def load_preset(self, preset_num: int) -> None:
        """Loads a hardware preset."""
        self._send(f"CCA X={preset_num}")
