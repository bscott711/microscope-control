# src/microscope/hardware/stage.py
from typing import Callable

from pymmcore_plus import CMMCorePlus

from ..config import HW, AcquisitionSettings


class StageController:
    """A controller for stage-specific hardware properties (e.g., Piezo)."""

    def __init__(self, mmc: CMMCorePlus, set_property: Callable):
        self.mmc = mmc
        self._set_property = set_property

    def configure_for_scan(self, settings: AcquisitionSettings, num_slices: int):
        """Configures the piezo stage for a scan."""
        piezo_label = HW.piezo_a_label
        piezo_pos = round(settings.piezo_center_um, 3)
        self._set_property(piezo_label, "SingleAxisAmplitude(um)", 0.0)
        self._set_property(piezo_label, "SingleAxisOffset(um)", piezo_pos)
        self._set_property(piezo_label, "SPIMNumSlices", num_slices)

    def set_idle(self):
        """Sets the piezo stage's SPIM state to Idle."""
        self._set_property(HW.piezo_a_label, "SPIMState", "Idle")

    def reset_position(self, settings: AcquisitionSettings):
        """Resets the piezo to its configured center position."""
        self._set_property(HW.piezo_a_label, "SingleAxisOffset(um)", settings.piezo_center_um)
