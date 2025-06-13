# src/microscope/hardware/galvo.py
from typing import Callable

from ..config import HW, AcquisitionSettings


class GalvoController:
    """A controller for the Galvo scanner card."""

    def __init__(self, set_property: Callable, execute_serial_command: Callable):
        self._set_property = set_property
        self._execute_serial_command = execute_serial_command

    def configure_for_scan(
        self,
        settings: AcquisitionSettings,
        galvo_amplitude: float,
        galvo_center: float,
        num_slices: int,
    ):
        """Configures all galvo properties for a SPIM scan."""
        galvo_label = HW.galvo_a_label
        galvo_card_addr = galvo_label.split(":")[2]

        self._execute_serial_command(f"{galvo_card_addr}TTL X=2 Y=1")
        self._set_property(galvo_label, "BeamEnabled", "Yes")
        self._set_property(galvo_label, "SPIMNumSlicesPerPiezo", HW.line_scans_per_slice)
        self._set_property(galvo_label, "SPIMDelayBeforeRepeat(ms)", HW.delay_before_scan_ms)
        self._set_property(galvo_label, "SPIMNumRepeats", 1)
        self._set_property(galvo_label, "SPIMDelayBeforeSide(ms)", HW.delay_before_side_ms)
        self._set_property(
            galvo_label,
            "SPIMAlternateDirectionsEnable",
            "Yes" if HW.scan_opposite_directions else "No",
        )
        self._set_property(galvo_label, "SPIMScanDuration(ms)", HW.line_scan_duration_ms)
        self._set_property(galvo_label, "SingleAxisYAmplitude(deg)", galvo_amplitude)
        self._set_property(galvo_label, "SingleAxisYOffset(deg)", galvo_center)
        self._set_property(galvo_label, "SPIMNumSlices", num_slices)
        self._set_property(galvo_label, "SPIMNumSides", HW.num_sides)
        self._set_property(galvo_label, "SPIMFirstSide", "A" if HW.first_side_is_a else "B")
        self._set_property(galvo_label, "SPIMPiezoHomeDisable", "No")
        self._set_property(galvo_label, "SPIMInterleaveSidesEnable", "No")
        self._set_property(galvo_label, "SingleAxisXAmplitude(deg)", HW.sheet_width_deg)
        self._set_property(galvo_label, "SingleAxisXOffset(deg)", HW.sheet_offset_deg)

    def arm(self):
        """Arms the galvo's SPIM state machine."""
        self._set_property(HW.galvo_a_label, "SPIMState", "Armed")

    def start(self):
        """Starts the galvo's SPIM state machine (sends the master trigger)."""
        self._set_property(HW.galvo_a_label, "SPIMState", "Running")

    def set_idle(self):
        """Sets the galvo's SPIM state to Idle and disables the beam."""
        self._set_property(HW.galvo_a_label, "BeamEnabled", "No")
        self._set_property(HW.galvo_a_label, "SPIMState", "Idle")
