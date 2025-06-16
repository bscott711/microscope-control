from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from .models import PLogicCardModel

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class ASIPLogicCommands:
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

    def __init__(self, plogic_device_label: str, mmc: CMMCorePlus) -> None:
        self._mmc = mmc
        self._label = plogic_device_label

    def _send(self, command: str):
        full_command = f"{self._label} {command}"
        self._mmc.setSerialPortCommand(self._mmc.getSerialPortName(self._label), full_command, "\r")
        response = self._mmc.getSerialPortAnswer(self._mmc.getSerialPortName(self._label), "\r")
        if ":N" in response:
            raise RuntimeError(f"ASI command failed: '{command}' -> {response}")

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
