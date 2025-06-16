from __future__ import annotations

from enum import IntEnum


class GalvoScanMode(IntEnum):
    """Mode for single-axis scanning (SAM command)."""

    SAWTOOTH = 0
    TRIANGLE = 1
    SAWTOOTH_TTL_GATED = 2
    TRIANGLE_TTL_GATED = 3


class GalvoLaserMode(IntEnum):
    """Laser output mode during scanning (LASER command)."""

    OFF = 0
    ON_DURING_SCAN = 4
