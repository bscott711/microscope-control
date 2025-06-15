import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

# Import type hints for clarity
from ..hardware.hal import HardwareAbstractionLayer
from ..ui.main_window import MainWindow


class AcquisitionWorker(QRunnable):
    """Worker thread for running an acquisition to keep the GUI responsive."""

    def __init__(self, hal: HardwareAbstractionLayer, settings: dict):
        super().__init__()
        self.hal = hal
        self.settings = settings

    @Slot()
    def run(self):
        """Execute the acquisition in the background."""
        try:
            self.hal.setup_and_run_z_stack(self.settings)
        except Exception:
            traceback.print_exc()


class AcquisitionEngine(QObject):
    """The Controller: connects the View to the Model (HAL)."""

    # Signals to be connected to the View's slots
    status_updated = Signal(str)
    acquisition_finished = Signal()
    acquisition_started = Signal()

    def __init__(self, hal: HardwareAbstractionLayer, view: MainWindow):
        super().__init__()
        self.hal = hal
        self.view = view  # Store a reference to the View
        self.thread_pool = QThreadPool()

        # --- Connect signals from the View to slots in this Controller ---
        self.view.start_acquisition_requested.connect(self.run_acquisition)
        self.view.cancel_acquisition_requested.connect(self.cancel_acquisition)

        # --- Connect signals from this Controller to slots in the View ---
        self.status_updated.connect(self.view.update_status)
        self.acquisition_started.connect(self.view.on_acquisition_started)
        self.acquisition_finished.connect(self.view.on_acquisition_finished)

        # --- Connect events from the Model (HAL/mmc) to slots in this Controller ---
        self.hal.mmc.mda.events.sequenceStarted.connect(self._on_mda_started)
        self.hal.mmc.mda.events.sequenceFinished.connect(self._on_mda_finished)
        self.hal.mmc.mda.events.frameReady.connect(self._on_frame_ready)

    @Slot(dict)
    def run_acquisition(self, settings: dict):
        """Creates and starts a worker to run the acquisition."""
        worker = AcquisitionWorker(self.hal, settings)
        self.thread_pool.start(worker)

    @Slot()
    def cancel_acquisition(self):
        """Stops a running MDA if one is active."""
        if self.hal.mmc.mda.is_running():
            self.status_updated.emit("Cancelling acquisition...")
            self.hal.mmc.mda.cancel()

    # --- Slots for Model Events ---
    @Slot(object)
    def _on_mda_started(self, sequence):
        self.acquisition_started.emit()

    @Slot(object)
    def _on_mda_finished(self, sequence):
        self.hal.final_cleanup()
        self.acquisition_finished.emit()

    @Slot(object, object)
    def _on_frame_ready(self, frame, event):
        current_slice = event.index.get("t", 0) + 1
        total_slices = event.sequence.t_loop
        self.status_updated.emit(f"Acquired Slice {current_slice} / {total_slices}")
