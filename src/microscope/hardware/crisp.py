from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus

from .asi_crisp import ASICrispCommands, CrispState

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class CrispController:
    """
    A final, high-level, state-aware controller for the ASI CRISP system.

    This class provides a clean, Pythonic interface to control CRISP. It
    exposes key parameters as properties and delegates all low-level serial
    command communication to the specialized `ASICrispCommands` class,
    which is available via the `.asi` attribute.
    """

    def __init__(
        self,
        device_label: str = "CRISP",
        mmc: CMMCorePlus | None = None,
    ) -> None:
        self._mmc = mmc or CMMCorePlus.instance()
        self.asi = ASICrispCommands(device_label, self._mmc)

    # --- Read-only State Properties ---
    @property
    def state(self) -> CrispState:
        """The current state of the CRISP system as a `CrispState` enum."""
        return self.asi.get_state()

    @property
    def is_locked(self) -> bool:
        """True if CRISP is in the 'In Lock' state."""
        return self.state == CrispState.In_Lock

    @property
    def snr(self) -> float:
        """The current Signal-to-Noise Ratio (SNR) / error number."""
        return self.asi.get_snr()

    # --- Read/Write Configuration Properties ---
    @property
    def loop_gain(self) -> int:
        """The controller's feedback loop gain."""
        return self.asi.get_gain()

    @loop_gain.setter
    def loop_gain(self, value: int):
        self.asi.set_gain(value)

    @property
    def led_intensity(self) -> int:
        """The intensity of the CRISP LED."""
        return self.asi.get_led_intensity()

    @led_intensity.setter
    def led_intensity(self, value: int):
        self.asi.set_led_intensity(value)

    @property
    def lock_range(self) -> float:
        """The focus lock range in microns."""
        return self.asi.get_lock_range()

    @lock_range.setter
    def lock_range(self, value: float):
        self.asi.set_lock_range(value)

    # --- High-Level Actions ---
    def lock(self, wait: bool = True, timeout_s: int = 10) -> bool:
        """Attempts to lock focus, optionally waiting for confirmation."""
        if self.is_locked:
            return True
        self.asi.lock()
        if not wait:
            return True
        start_time = time.time()
        while time.time() - start_time < timeout_s:
            if self.is_locked:
                return True
            time.sleep(0.1)
        return False

    def unlock(self):
        self.asi.unlock()

    def calibrate(self):
        """Runs the full 3-step CRISP calibration routine."""
        print("Starting CRISP calibration...")
        self.unlock()
        time.sleep(0.5)
        self.asi.calibrate_log_amp()
        time.sleep(2)
        self.asi.dither()
        time.sleep(2)
        self.asi.calibrate_gain()
        time.sleep(2)
        print("Calibration complete.")
