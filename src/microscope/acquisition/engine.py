# src/microscope/acquisition/engine.py
"""
Custom MDA engine for PLogic-driven SPIM acquisitions.
Manages the acquisition lifecycle, frame buffering, and scrubbing.
"""

import logging

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from qtpy.QtCore import Qt, QThread
from useq import MDASequence

from microscope.acquisition.worker import AcquisitionWorker
from microscope.model.hardware_model import HardwareConstants

# Set up logger
logger = logging.getLogger(__name__)


class PLogicMDAEngine(MDAEngine):
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self, mmc: CMMCorePlus, hw_constants: HardwareConstants):
        """Initialize the engine with the core instance and hardware constants.
        Args:
            mmc: The Micro-Manager core instance
            hw: HardwareConstants object containing device labels and configuration
        """
        super().__init__(mmc)
        self._mmc = mmc
        self.HW = hw_constants
        self._worker = None
        self._thread = None
        self._frame_buffer = {}
        self._display_t = 0
        self._display_z = 0
        self._sequence = None

    def run(self, sequence: MDASequence):
        """Run an MDA sequence, delegating to the correct method."""
        self._sequence = sequence
        self._frame_buffer.clear()
        self._display_t = 0
        self._display_z = 0

        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})
            self._worker = AcquisitionWorker(self._mmc, sequence, self.HW)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            # Connect signals
            self._worker.frameReady.connect(self._on_frame_ready, Qt.ConnectionType.QueuedConnection)
            self._thread.started.connect(self._worker.run)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine")
            self._mmc.run_mda(sequence)

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            result = current_focus_device == self.HW.piezo_a_label
            logger.debug(
                "Checking Core Focus. Current: '%s'. Required: '%s'. Use PLogic? %s",
                current_focus_device,
                self.HW.piezo_a_label,
                result,
            )
            return result
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _on_frame_ready(self, frame, event, meta):
        """
        Slot to handle the frameReady signal from the worker.

        This method buffers the frame for later scrubbing and immediately emits the
        global frameReady event. This ensures that all data is saved and the
        live view is continuously updated.
        """
        if not self._sequence:
            return

        # Buffer the frame using a key derived from its full index.
        # The worker forces the axis order to ('t', 'p', 'z', 'c').
        key = (
            event.index.get("t", 0),
            event.index.get("p", 0),
            event.index.get("z", 0),
            event.index.get("c", 0),
        )
        self._frame_buffer[key] = (frame, event, meta)

        # Immediately emit the signal for all frames. This is crucial for
        # saving data and for the default live view.
        self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def set_displayed_slice(self, t: int, z: int):
        """
        Request a specific t- and z-slice to be displayed.

        If the requested frame is found in the buffer, it is emitted via the
        frameReady signal to update the display. This allows for scrubbing
        during or after the acquisition. This implementation assumes you want to
        view the first channel and first position for the given t/z.
        """
        if not self._sequence:
            return

        self._display_t = t
        self._display_z = z

        # Construct the key for the requested frame, assuming channel 0, position 0.
        # The worker forces the axis order to ('t', 'p', 'z', 'c').
        lookup_key = (t, 0, z, 0)

        if lookup_key in self._frame_buffer:
            frame, event, meta = self._frame_buffer[lookup_key]
            # Emit the specific buffered frame to update the viewer.
            self._mmc.mda.events.frameReady.emit(frame, event, meta)
            logger.debug("Re-displaying buffered frame for t=%d, z=%d", t, z)
        else:
            # This is not an error; the frame may not have been acquired yet.
            logger.debug("Frame for t=%d, z=%d not yet in buffer.", t, z)

    def _on_acquisition_finished(self, sequence):
        """Slot to handle the acquisitionFinished signal from the worker."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._mmc.mda.events.sequenceFinished.emit(sequence)
