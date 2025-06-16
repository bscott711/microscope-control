from __future__ import annotations

from enum import IntEnum


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
