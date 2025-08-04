# src/microscope/acquisition/worker.py
"""
Worker for running the hardware-timed collection loop of an MDA.
Runs in a separate thread and emits frames as they are collected.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, Signal  # type: ignore
from useq import MDAEvent, MDASequence

from microscope.hardware import trigger_spim_scan_acquisition
from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


@dataclass
class TimingParams:
    """A simple container for calculated acquisition timing parameters."""

    num_z_slices: int
    num_timepoints: int
    repeat_delay_ms: float
    total_images: int


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
        params: TimingParams,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.hw = hw_constants
        self.params = params
        self._running = True

    def stop(self) -> None:
        """Flags the acquisition to stop gracefully."""
        logger.info("Stop requested for acquisition worker.")
        self._running = False

    def run(self) -> None:
        """
        Triggers the hardware sequence and collects incoming frames.
        This method is designed to be run in a separate QThread.
        """
        try:
            self._mmc.startSequenceAcquisition(self.hw.camera_a_label, self.params.total_images, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.hw)

            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for _ in range(self.params.total_images):
                if not self._running:
                    logger.info("Acquisition stopped by user.")
                    break

                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning():
                        logger.error("Camera sequence stopped unexpectedly.")
                        break
                    time.sleep(0.001)

                tagged_img = self._mmc.popNextTaggedImage()
                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug("Frame collected: %s", event.index)

        except Exception as _:
            logger.critical("Acquisition loop failed due to an unexpected error.", exc_info=True)
        finally:
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Acquisition worker finished.")
