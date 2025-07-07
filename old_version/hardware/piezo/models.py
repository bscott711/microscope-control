# hardware/piezo/models.py
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


# Your original, correct Enum classes
class PiezoMode(IntEnum):
    """Operating mode for the Piezo stage (PZ Z or PM command)."""

    CLOSED_LOOP_INTERNAL = 0
    CLOSED_LOOP_EXTERNAL = 1
    OPEN_LOOP_INTERNAL = 2
    OPEN_LOOP_EXTERNAL = 3


class PiezoMaintainMode(IntEnum):
    """Maintain mode for ADEPT Piezo cards (MA command)."""

    DEFAULT = 0
    OVERSHOOT_ALGORITHM = 1


# The new dataclass that was missing
@dataclass
class PiezoInfo:
    """A data class to hold information about the piezo stage."""

    axis: str
    limit_min: float
    limit_max: float
    current_pos: float
