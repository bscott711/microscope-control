# src/microscope/hardware/galvo.py
from typing import Callable

from ..config import HW, AcquisitionSettings


class GalvoController:
    """A controller for the Galvo scanner card."""

    def __init__(self, set_property: Callable):
        """
        Initializes the GalvoController.

        Args:
            set_property: A function to set a device property.
        """
        self._set_property = set_property
        self.label = HW.galvo_a_label

    def configure_for_scan(self, settings: AcquisitionSettings):
        """Configures all galvo properties based on the validated log file."""
        print("Configuring Galvo scanner with validated sequence...")
        self._set_property(self.label, "BeamEnabled", "No")
        self._set_property(self.label, "SPIMNumSlicesPerPiezo", 1)
        self._set_property(self.label, "SPIMDelayBeforeRepeat(ms)", 0)
        self._set_property(self.label, "SPIMNumRepeats", 1)
        self._set_property(self.label, "SPIMDelayBeforeSide(ms)", 1)
        # The laser trigger duration is the same as the scan duration in this mode.
        self._set_property(self.label, "SPIMScanDuration(ms)", settings.laser_trig_duration_ms)
        self._set_property(self.label, "SPIMNumSlices", settings.num_slices)
        self._set_property(self.label, "SPIMNumSides", 1)
        self._set_property(self.label, "SPIMFirstSide", "A")
        self._set_property(self.label, "SPIMPiezoHomeDisable", "No")
        self._set_property(self.label, "SPIMInterleaveSidesEnable", "No")

    def start(self):
        """Starts the galvo's SPIM state machine (sends the master trigger)."""
        self._set_property(self.label, "SPIMState", "Running")

    def set_idle(self):
        """Sets the galvo's SPIM state to Idle and disables the beam."""
        self._set_property(self.label, "BeamEnabled", "No")
        self._set_property(self.label, "SPIMState", "Idle")
