# hardware/engine/state.py
from enum import Enum, auto


class AcquisitionState(Enum):
    """Defines the possible states of the acquisition worker."""

    IDLE = auto()
    PREPARING = auto()
    ACQUIRING = auto()
    PAUSED = auto()
    CLEANING_UP = auto()
    FINISHED = auto()
    CANCELLED = auto()
    ERROR = auto()
