# src/microscope/acquisition/worker.py
"""
Worker for running the hardware-timed collection loop of an MDA.
Runs in a separate thread and emits frames as they are collected.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, Signal, Slot  # type: ignore
from useq import MDAEvent, MDASequence

from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


class AcquisitionWorker(QObject):
    """
    Worker object for running the hardware-timed acquisition loop.
    """

    frameReady = Signal(object, MDAEvent, dict)
    acquisitionFinished = Signal(MDASequence)

    def __init__(
        self,
        mmc: CMMCorePlus,
        sequence: MDASequence,
        hw_constants: HardwareConstants,
        total_images: int,
        parent=None,
    ):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.hw = hw_constants
        self.total_images = total_images
        self._running = True

    def stop(self) -> None:
        """Flags the acquisition to stop gracefully."""
        logger.info("Stop requested for acquisition worker.")
        self._running = False

    @Slot()
    def run(self) -> None:
        """
        Executes the image collection loop for a hardware-timed sequence.
        Assumes hardware has already been configured and started by the engine.
        """
        try:
            logger.info("Acquisition worker now polling for frames.")

            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for _ in range(self.total_images):
                if not self._running:
                    logger.info("Acquisition stopped by user.")
                    break

                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning():
                        logger.error("Camera sequence stopped unexpectedly.")
                        break
                    time.sleep(0.001)

                if not self._mmc.isSequenceRunning() and self._mmc.getRemainingImageCount() == 0:
                    break

                tagged_img = self._mmc.popNextTaggedImage()
                if tagged_img is None:
                    logger.warning("Popped a null image, continuing.")
                    continue

                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug("Frame collected: %s", event.index)

        except Exception as _:
            logger.critical("Acquisition loop failed due to an unexpected error.", exc_info=True)
        finally:
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Acquisition worker finished.")
