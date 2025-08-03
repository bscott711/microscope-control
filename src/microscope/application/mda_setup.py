# src/microscope/application/mda_setup.py
"""
mda_setup.py
Responsible for wiring the MDA widget to the custom PLogic MDA engine.
This isolates the complex MDA setup logic from the main application controller.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMETiffWriter,
    OMEZarrWriter,
)
from useq import MDASequence

from microscope.acquisition import PLogicMDAEngine
from microscope.model.hardware_model import HardwareConstants

# Use TYPE_CHECKING to avoid circular import at runtime
if TYPE_CHECKING:
    from pymmcore_widgets.mda import MDAWidget

logger = logging.getLogger(__name__)


class OMETiffWriterWithMetadata(OMETiffWriter):
    """Extends OMETiffWriter to save metadata JSON files alongside the OME-TIFF."""

    def __init__(self, filename: str):
        super().__init__(filename)
        self._basename = Path(filename).with_suffix("").name

    def sequenceStarted(self, seq: MDASequence, meta: object = object()):
        super().sequenceStarted(seq, meta)
        self._meta_dir = Path(self._filename).parent
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        seq_path = self._meta_dir / f"{self._basename}_useq_MDASequence.json"
        seq_path.write_text(seq.model_dump_json(indent=2))

    def sequenceFinished(self, seq: MDASequence):
        super().sequenceFinished(seq)
        if hasattr(self, "frame_metadatas") and self.frame_metadatas:
            import json

            from pymmcore_plus.metadata import to_builtins

            serializable_meta = {
                pos_key: [to_builtins(m) for m in metas] for pos_key, metas in self.frame_metadatas.items()
            }
            meta_path = self._meta_dir / f"{self._basename}_frame_metadata.json"
            meta_path.write_text(json.dumps(serializable_meta, indent=2))


def setup_mda_widget(
    mda_widget: "MDAWidget",  # Type hint for the MDA widget
    mmc: CMMCorePlus,
    hw: HardwareConstants,
    save_handler: Optional[Union[OMETiffWriter, OMEZarrWriter, ImageSequenceWriter]] = None,
):
    """
    Wires the MDA widget to use the CustomPLogicMDAEngine.
    Args:
        mda_widget: The MDA widget from pymmcore-gui
        mmc: Core instance
        hw: HardwareConstants instance
        save_handler: Optional pre-configured save handler
    """
    engine = PLogicMDAEngine(mmc, hw)
    mmc.register_mda_engine(engine)
    logger.info("Custom PLogic MDA Engine registered.")

    def mda_runner(output=None):
        # Type-safe access to the widget's value
        sequence: MDASequence = mda_widget.value()
        save_info = mda_widget.save_info.value()

        handler = save_handler
        if not handler and save_info["should_save"]:
            save_path = Path(save_info["save_dir"]) / save_info["save_name"]
            if save_path.suffix.lower() in {".zarr", ".ome.zarr"}:
                handler = OMEZarrWriter(save_path, overwrite=True)
            elif save_path.suffix.lower() in {".tif", ".tiff", ".ome.tif", ".ome.tiff"}:
                handler = OMETiffWriterWithMetadata(str(save_path))
            else:
                handler = ImageSequenceWriter(save_path)

        # Connect handler to MDA events
        if handler:
            mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
            mmc.mda.events.frameReady.connect(handler.frameReady)
            mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)

            # Disconnect after finished
            def _disconnect():
                mmc.mda.events.sequenceStarted.disconnect(handler.sequenceStarted)
                mmc.mda.events.frameReady.disconnect(handler.frameReady)
                mmc.mda.events.sequenceFinished.disconnect(handler.sequenceFinished)
                mmc.mda.events.sequenceFinished.disconnect(_disconnect)

            mmc.mda.events.sequenceFinished.connect(_disconnect)

        engine.run(sequence)

    # Safe assignment with attribute check
    if hasattr(mda_widget, "execute_mda"):
        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        logger.error("MDA widget does not have 'execute_mda' attribute.")
