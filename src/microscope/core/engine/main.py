# src/microscope/core/engine/main.py

import logging

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from qtpy.QtCore import QThread
from useq import MDASequence

from .worker import AcquisitionWorker

logger = logging.getLogger(__name__)


class CustomPLogicMDAEngine(MDAEngine):
    """
    Custom MDA engine that uses a QThread to run PLogic-driven acquisitions.

    This engine decides whether to use the custom hardware-timed acquisition
    path or fall back to the default MDA engine. It manages the lifecycle
    of the AcquisitionWorker thread and handles buffering frames for display.
    """

    def __init__(self):
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self._worker = None
        self._thread = None
        self._frame_buffer = {}
        self._sequence = None

    def run(self, sequence: MDASequence):
        """
        Run an MDA sequence, delegating to the appropriate method.
        """
        self._sequence = sequence
        self._frame_buffer.clear()

        if self._should_use_plogic():
            logger.info("Running custom PLogic Z-stack sequence.")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})
            self._worker = AcquisitionWorker(self._mmc, sequence)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            # Connect signals from worker to this engine's slots
            self._worker.frameReady.connect(self._on_frame_ready)
            self._thread.started.connect(self._worker.run)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine.")
            super().run(sequence)  # type: ignore

    def _should_use_plogic(self) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            return current_focus_device == "PiezoStage:P:34"
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _on_frame_ready(self, frame, event, meta):
        """
        Slot to handle the frameReady signal from the worker.

        This method buffers the frame and immediately emits the global
        frameReady event for data saving and live view updates.
        """
        if not self._sequence:
            return

        key = tuple(event.index.get(k, 0) for k in self._sequence.axis_order)
        self._frame_buffer[key] = (frame, event, meta)
        self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def _on_acquisition_finished(self, sequence):
        """Slot to handle the acquisitionFinished signal from the worker."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._mmc.mda.events.sequenceFinished.emit(sequence)
