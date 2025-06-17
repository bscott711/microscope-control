# hardware/crisp/models.py
from __future__ import annotations

from enum import IntEnum


class CrispState(IntEnum):
    """An enumeration of the possible states of the CRISP system."""

    Idle = 3
    Log_Amp_Cal = 4
    Dithering = 5
    Gain_Cal = 6
    Ready = 7
    In_Focus = 8
    Focal_Plane_Found = 9
    Monitoring = 10
    Focusing = 11
    In_Lock = 12
    Focus_Lost_Recently = 13
    Out_Of_Focus = 14
    Focus_Lost = 15
