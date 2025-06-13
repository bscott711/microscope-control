# src/microscope/hardware/stage.py
from typing import Callable

from pymmcore_plus import CMMCorePlus

from ..config import HW, AcquisitionSettings


class StageController:
    """A controller for stage-specific hardware properties (e.g., Piezo)."""

    def __init__(self, mmc: CMMCorePlus, set_property: Callable):
        self.mmc = mmc
        self._set_property = set_property
        self.label = HW.piezo_a_label

    def configure_for_scan(self, settings: AcquisitionSettings):
        """
        No-op. In the validated log sequence, the piezo is controlled
        by the scanner card's SPIM state machine, not direct properties.
        """
        pass

    def set_idle(self):
        """Sets the piezo stage's SPIM state to Idle."""
        self._set_property(self.label, "SPIMState", "Idle")

    def reset_position(self, settings: AcquisitionSettings):
        """Resets the piezo to its configured center position."""
        self._set_property(self.label, "SingleAxisOffset(um)", settings.piezo_center_um)
