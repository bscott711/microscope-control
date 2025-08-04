# src/microscope/application/mda_setup.py
"""
mda_setup.py
Responsible for wiring the MDA widget to the custom PLogic MDA engine.
This isolates the complex MDA setup logic from the main application controller.
"""

import json
import logging
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMETiffWriter,
    OMEZarrWriter,
)
from pymmcore_plus.metadata import FrameMetaV1, to_builtins
from useq import MDAEvent, MDASequence

from microscope.acquisition import PLogicMDAEngine
from microscope.model.hardware_model import HardwareConstants

if TYPE_CHECKING:
    from pymmcore_widgets.mda import MDAWidget

logger = logging.getLogger(__name__)

TIFF_EXTENSIONS = {".tif", ".tiff", ".ome.tif", ".ome.tiff"}
ZARR_EXTENSIONS = {".zarr", ".ome.zarr"}
AnyWriter = OMETiffWriter | OMEZarrWriter | ImageSequenceWriter


class OMETiffWriterWithMetadata(OMETiffWriter):
    """Extends OMETiffWriter to save comprehensive metadata JSON files."""

    def __init__(self, filename: str) -> None:
        super().__init__(filename)
        self._basename = Path(filename).with_suffix("").name
        self.frame_metadatas: defaultdict[str, list[FrameMetaV1]] = defaultdict(list)

    def sequenceStarted(self, seq: MDASequence, meta: object = object()) -> None:
        super().sequenceStarted(seq, meta)
        self._meta_dir = Path(self._filename).parent
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        seq_path = self._meta_dir / f"{self._basename}_useq_MDASequence.json"
        seq_path.write_text(seq.model_dump_json(indent=2))

    # FIX: The `meta` parameter's type hint must match the base class.
    # At runtime, it's a dict, but the type hint must be FrameMetaV1.
    def frameReady(self, frame: np.ndarray, event: MDAEvent, meta: FrameMetaV1) -> None:
        super().frameReady(frame, event, meta)
        key = str(event.index.get("p", 0))
        self.frame_metadatas[key].append(meta)

    def sequenceFinished(self, seq: MDASequence) -> None:
        super().sequenceFinished(seq)
        if not self.frame_metadatas:
            return
        serializable_meta = {
            pos_key: [to_builtins(m) for m in metas] for pos_key, metas in self.frame_metadatas.items()
        }
        meta_path = self._meta_dir / f"{self._basename}_frame_metadata.json"
        meta_path.write_text(json.dumps(serializable_meta, indent=2))


def _create_mda_handler(save_info: Mapping[str, Any]) -> Optional[AnyWriter]:
    """Creates a file writer based on the save_info from the MDA widget."""
    if not save_info.get("should_save"):
        return None

    save_path = Path(str(save_info["save_dir"])) / str(save_info["save_name"])
    ext = save_path.suffix.lower()

    if ext in ZARR_EXTENSIONS:
        return OMEZarrWriter(str(save_path), overwrite=True)
    if ext in TIFF_EXTENSIONS:
        return OMETiffWriterWithMetadata(str(save_path))

    return ImageSequenceWriter(str(save_path))


def setup_mda_widget(
    mda_widget: "MDAWidget",
    mmc: CMMCorePlus,
    hw: HardwareConstants,
    save_handler: Optional[AnyWriter] = None,
) -> PLogicMDAEngine:
    """
    Wires the MDA widget to use the CustomPLogicMDAEngine.
    """
    engine = PLogicMDAEngine(mmc, hw)
    mmc.register_mda_engine(engine)
    logger.info("Custom PLogic MDA Engine registered.")

    def mda_runner(output: Optional[Any] = None) -> None:
        sequence: MDASequence = mda_widget.value()
        save_info = mda_widget.save_info.value()
        handler = save_handler or _create_mda_handler(save_info)

        if handler:
            mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
            mmc.mda.events.frameReady.connect(handler.frameReady)
            mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)

            def _disconnect() -> None:
                mmc.mda.events.sequenceStarted.disconnect(handler.sequenceStarted)
                mmc.mda.events.frameReady.disconnect(handler.frameReady)
                mmc.mda.events.sequenceFinished.disconnect(handler.sequenceFinished)
                mmc.mda.events.sequenceFinished.disconnect(_disconnect)

            mmc.mda.events.sequenceFinished.connect(_disconnect)

        engine.run(sequence)

    if hasattr(mda_widget, "execute_mda"):
        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button wired to use CustomPLogicMDAEngine.")
    else:
        logger.error("MDA widget does not have 'execute_mda' attribute.")

    return engine
