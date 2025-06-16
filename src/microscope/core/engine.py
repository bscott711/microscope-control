from __future__ import annotations

import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal
from qtpy.QtCore import QRunnable, QThreadPool

if TYPE_CHECKING:
    from microscope.config import AcquisitionSettings
    from microscope.hardware.hal import HardwareAbstractionLayer


class AcquisitionWorker(QRunnable):
    """
    Worker that executes a fully autonomous, GALVO-DRIVEN, hardware-timed
    acquisition. Its job is to configure all hardware components, start the
    galvo scan (which initiates the entire PLogic-controlled sequence), and
    then collect the resulting images from the camera's buffer.
    """

    def __init__(self, hal: HardwareAbstractionLayer, settings: AcquisitionSettings):
        super().__init__()
        self.hal = hal
        self.settings = settings
        self.signals = AcquisitionSignals()
        self.is_cancelled = False

    def run(self) -> None:
        """Configures, triggers, and collects data from the autonomous sequence."""
        self.signals.acquisition_started.emit()

        if not all([self.hal.camera, self.hal.scanner, self.hal.plogic]):
            print("ERROR: Required hardware (Camera, Scanner, PLogic) not found.")
            self.signals.acquisition_finished.emit()
            return

        # 1. --- HARDWARE CONFIGURATION PHASE ---
        print("INFO: Configuring hardware for galvo-driven acquisition...")

        # A. Configure PLogic to listen to the galvo's TTL pulse
        # The galvo sync signal is on backplane TTL line 5 (address 46).
        # Trigger source code 2 on the PLogic card corresponds to this line.
        self.hal.plogic.asi.set_trigger_source(source_code=2)

        # B. Program the PLogic card with the full MDA sequence logic.
        # This configures how the PLogic card will react to each incoming
        # galvo trigger to control the camera and lasers.
        self.hal.plogic.configure_for_mda(self.settings)

        # C. Configure the galvo to perform the desired scan pattern AND
        # to output a TTL pulse at the start/end of each line, which will
        # trigger the PLogic card.
        self.hal.scanner.setup_raster_scan(
            # ... scan parameters from settings ...
        )
        self.hal.scanner.asi.set_ttl_output_mode(self.hal.scanner.x_axis, mode=2)

        # D. Configure the camera for the total number of frames and
        # put it in a hardware-trigger-ready state.
        total_frames = (
            self.settings.num_timepoints
            * (self.settings.z_stack.steps if self.settings.z_stack else 1)
            * len(self.settings.channels)
        )
        self.hal.camera.start_sequence_acquisition(num_images=total_frames)

        # 2. --- TRIGGER AND DATA COLLECTION PHASE ---
        print("INFO: Starting galvo scan to initiate autonomous MDA...")

        # This is the ONLY command that starts the action. The galvos will now
        # start scanning, which sends TTL pulses to the PLogic card. The PLogic
        # card then takes over and orchestrates the camera and lasers.
        self.hal.scanner.start()

        frames_collected = 0
        while frames_collected < total_frames and not self.is_cancelled:
            image = self.hal.camera.pop_from_buffer()
            if image is not None:
                frames_collected += 1
                # ... emit signals for progress and acquired frames ...
            else:
                time.sleep(0.001)  # Poll the buffer gently

        # 3. --- CLEANUP ---
        self.hal.scanner.stop()
        self.hal.camera.stop_sequence_acquisition()
        print("INFO: Galvo-driven acquisition finished.")
        self.signals.acquisition_finished.emit()


# The AcquisitionSignals and AcquisitionEngine classes remain the same
# as they are simply for managing the worker and its signals.
class AcquisitionSignals(QObject):
    acquisition_started = Signal()
    acquisition_progress = Signal(int)
    frame_acquired = Signal(object, dict)
    acquisition_finished = Signal()


class AcquisitionEngine(QObject):
    def __init__(self, hal: HardwareAbstractionLayer) -> None:
        super().__init__()
        self.hal = hal
        self.thread_pool = QThreadPool()
        self.worker: AcquisitionWorker | None = None
        self.signals = AcquisitionSignals()

    def run_acquisition(self, settings: AcquisitionSettings):
        if self.worker and not self.worker.is_cancelled:
            print("WARNING: An acquisition is already running.")
            return
        self.worker = AcquisitionWorker(self.hal, settings)
        self.worker.signals.acquisition_started.connect(self.signals.acquisition_started)
        self.worker.signals.acquisition_progress.connect(self.signals.acquisition_progress)
        self.worker.signals.frame_acquired.connect(self.signals.frame_acquired)
        self.worker.signals.acquisition_finished.connect(self.signals.acquisition_finished)
        self.thread_pool.start(self.worker)

    def cancel_acquisition(self):
        if self.worker:
            self.worker.is_cancelled = True
