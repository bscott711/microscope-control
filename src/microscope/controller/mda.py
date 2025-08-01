# src/microscope/controller/mda.py

from pathlib import Path
from typing import Optional, Union

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import ImageSequenceWriter, OMEZarrWriter
from useq import MDASequence

from microscope.core import OMETiffWriterWithMetadata


class MDAController:
    """
    Controller for running Multi-Dimensional Acquisitions (MDA).
    """

    def __init__(self, main_controller):
        self.mmc = main_controller.mmc
        self.window = main_controller.window
        self._handler_manager = None

    def run_mda(self, sequence: Optional[MDASequence] = None):
        """
        Prepares and executes an MDA sequence with the appropriate data handler.
        """
        mda_widget = self.window.mda_widget
        if not mda_widget:
            return

        if sequence is None:
            sequence = mda_widget.value()

        save_info = mda_widget.save_info.value()
        handler = None
        if save_info["should_save"]:
            save_path = Path(save_info["save_dir"]) / save_info["save_name"]
            if save_path.suffix in {".zarr", ".ome.zarr"}:
                handler = OMEZarrWriter(save_path, overwrite=True)
            elif save_path.suffix in {".tif", ".tiff", ".ome.tif", ".ome.tiff"}:
                handler = OMETiffWriterWithMetadata(str(save_path))
            else:
                handler = ImageSequenceWriter(save_path)

        # The handler manager will be garbage collected after the sequence,
        # disconnecting the handler from the events.
        self._handler_manager = HandlerManager(self.mmc, handler)
        self.mmc.mda.engine.run(sequence)


class HandlerManager:
    """
    Manages the connection of a data-saving handler to the MDA event bus.
    """

    def __init__(
        self,
        mmc: CMMCorePlus,
        handler: Optional[Union[OMEZarrWriter, OMETiffWriterWithMetadata, ImageSequenceWriter]],
    ):
        self.mmc = mmc
        self.handler = handler
        if self.handler:
            self.mmc.mda.events.sequenceStarted.connect(self.handler.sequenceStarted)
            self.mmc.mda.events.frameReady.connect(self.handler.frameReady)
            self.mmc.mda.events.sequenceFinished.connect(self.handler.sequenceFinished)
        self.mmc.mda.events.sequenceFinished.connect(self._disconnect)

    def _disconnect(self, sequence: MDASequence):
        """Disconnects the handler from MDA events."""
        if self.handler:
            self.mmc.mda.events.sequenceStarted.disconnect(self.handler.sequenceStarted)
            self.mmc.mda.events.frameReady.disconnect(self.handler.frameReady)
            self.mmc.mda.events.sequenceFinished.disconnect(self.handler.sequenceFinished)
        self.mmc.mda.events.sequenceFinished.disconnect(self._disconnect)
