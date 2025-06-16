from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class PLogicCellType(IntEnum):
    """Enumeration of all 16 possible logic cell types."""

    GND = 0
    VCC = 1
    AND = 2
    NAND = 3
    OR = 4
    NOR = 5
    XOR = 6
    XNOR = 7
    INVERTER = 8
    D_FLIP_FLOP = 9
    R_S_FLIP_FLOP = 10
    D_LATCH = 11
    COUNTER = 12
    ONE_SHOT = 13
    DELAY = 14
    LUT_4_INPUT = 15


class PLogicIOType(IntEnum):
    """Direction for a physical I/O port."""

    INPUT = 0
    OUTPUT_OPEN_DRAIN = 1
    OUTPUT_PUSH_PULL = 2


class PLogicAddress(IntEnum):
    """
    A comprehensive mapping of PLogic features to their hardware address codes.
    These are the values written to the controller to select an input/output source.
    See Appendix A: Memory Map in the TGPLC documentation.
    """

    # Outputs of the 16 logic cells
    CELL_1_OUT = 48
    CELL_2_OUT = 49
    CELL_3_OUT = 50
    CELL_4_OUT = 51
    CELL_5_OUT = 52
    CELL_6_OUT = 53
    CELL_7_OUT = 54
    CELL_8_OUT = 55
    CELL_9_OUT = 56
    CELL_10_OUT = 57
    CELL_11_OUT = 58
    CELL_12_OUT = 59
    CELL_13_OUT = 60
    CELL_14_OUT = 61
    CELL_15_OUT = 62
    CELL_16_OUT = 63
    # Inputs from the 8 BNC connectors
    BNC_1_IN = 32
    BNC_2_IN = 33
    BNC_3_IN = 34
    BNC_4_IN = 35
    BNC_5_IN = 36
    BNC_6_IN = 37
    BNC_7_IN = 38
    BNC_8_IN = 39
    # Inputs from the 8 backplane TTL lines
    TTL_1_IN = 80
    TTL_2_IN = 81
    TTL_3_IN = 82
    TTL_4_IN = 83
    TTL_5_IN = 84
    TTL_6_IN = 85
    TTL_7_IN = 86
    TTL_8_IN = 87
    # Other useful addresses
    GND = 0
    VCC = 1
    Clock_4kHz = 2
    Clock_2kHz = 3


@dataclass
class PLogicCell:
    """Represents the configuration of a single logic cell."""

    cell_type: PLogicCellType = PLogicCellType.GND
    config_value: int = 0
    inputs: list[PLogicAddress] = field(default_factory=lambda: [PLogicAddress.GND] * 4)


@dataclass
class PLogicIOPort:
    """Represents the configuration of a single I/O port (BNC or TTL)."""

    direction: PLogicIOType = PLogicIOType.INPUT
    output_source: PLogicAddress = PLogicAddress.GND


@dataclass
class PLogicCardModel:
    """A complete model of the PLogic card's programmable state."""

    cells: list[PLogicCell] = field(default_factory=lambda: [PLogicCell() for _ in range(16)])
    bnc_ports: list[PLogicIOPort] = field(default_factory=lambda: [PLogicIOPort() for _ in range(8)])
    ttl_ports: list[PLogicIOPort] = field(default_factory=lambda: [PLogicIOPort() for _ in range(8)])
