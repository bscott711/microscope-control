# hardware/engine/manager.py
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .plans import AcquisitionPlan
from .state import AcquisitionState

if TYPE_CHECKING:
    from microscope.config import AcquisitionSettings, HardwareConstants
    from microscope.hardware.hal import HardwareAbstractionLayer


class AcquisitionSignals(QObject):
    """Signals emitted by the acquisition worker."""

    state_changed = Signal(AcquisitionState)
    frame_acquired = Signal(object, dict)  # image, metadata
    acquisition_finished = Signal()
    acquisition_error = Signal(str)


class AcquisitionWorker(QRunnable):
    """
    Worker that executes an acquisition plan using a state machine.
    """

    def __init__(
        self,
        hal: HardwareAbstractionLayer,
        plan: AcquisitionPlan,
        settings: AcquisitionSettings,
        hw_constants: HardwareConstants,
    ):
        super().__init__()
        self.hal = hal
        self.plan = plan
        self.settings = settings
        self.hw_constants = hw_constants
        self.signals = AcquisitionSignals()
        self.state = AcquisitionState.IDLE
        self._cancelled = False

    def run(self) -> None:
        """The main entry point for the acquisition thread."""
        try:
            # 1. PREPARATION
            self._set_state(AcquisitionState.PREPARING)
            self.plan.pre_acquisition_setup(self.hal, self.settings, self.hw_constants)

            # 2. ACQUISITION
            self._set_state(AcquisitionState.ACQUIRING)
            total_frames = self.settings.num_slices * self.settings.time_points
            frames_collected = 0
            while frames_collected < total_frames and not self._cancelled:
                # Correctly call getRemainingImageCount on the mmc object
                if self.hal.camera and self.hal.camera._mmc.getRemainingImageCount() > 0:
                    image = self.hal.camera.pop_from_buffer()
                    if image is not None:
                        self.signals.frame_acquired.emit(image, {})
                        frames_collected += 1
                else:
                    time.sleep(0.005)  # Small sleep to prevent busy-waiting

            if self._cancelled:
                self._set_state(AcquisitionState.CANCELLED)
            else:
                self._set_state(AcquisitionState.FINISHED)

        except Exception as e:
            self._set_state(AcquisitionState.ERROR)
            self.signals.acquisition_error.emit(str(e))
        finally:
            # 3. CLEANUP
            self._set_state(AcquisitionState.CLEANING_UP)
            self.plan.post_acquisition_cleanup(self.hal)
            self._set_state(AcquisitionState.IDLE)
            self.signals.acquisition_finished.emit()

    def cancel(self):
        """Requests cancellation of the acquisition."""
        self._cancelled = True

    def _set_state(self, state: AcquisitionState):
        self.state = state
        self.signals.state_changed.emit(state)


class AcquisitionEngine(QObject):
    """
    Manages the acquisition worker and thread pool.
    """

    def __init__(
        self,
        hal: HardwareAbstractionLayer,
        hw_constants: HardwareConstants,
    ) -> None:
        super().__init__()
        self.hal = hal
        self.hw_constants = hw_constants
        self.thread_pool = QThreadPool()
        self.worker: AcquisitionWorker | None = None
        self.signals = AcquisitionSignals()

    def run_acquisition(self, plan: AcquisitionPlan, settings: AcquisitionSettings):
        """Runs a given acquisition plan with the specified settings."""
        if self.worker and self.worker.state != AcquisitionState.IDLE:
            print("WARNING: An acquisition is already running.")
            return

        self.worker = AcquisitionWorker(self.hal, plan, settings, self.hw_constants)
        # Connect worker signals to the engine's public signals
        self.worker.signals.state_changed.connect(self.signals.state_changed)
        self.worker.signals.frame_acquired.connect(self.signals.frame_acquired)
        self.worker.signals.acquisition_finished.connect(self.signals.acquisition_finished)
        self.worker.signals.acquisition_error.connect(self.signals.acquisition_error)
        self.thread_pool.start(self.worker)

    def cancel_acquisition(self):
        """Cancels the currently running acquisition."""
        if self.worker:
            self.worker.cancel()
