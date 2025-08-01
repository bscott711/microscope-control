# src/microscope/core/datastore.py

import json
from pathlib import Path

from pymmcore_plus.mda.handlers import OMETiffWriter
from pymmcore_plus.metadata import SummaryMetaV1, to_builtins
from useq import MDASequence


class OMETiffWriterWithMetadata(OMETiffWriter):
    """
    Extends OMETiffWriter to save metadata JSON files alongside the OME-TIFF.

    This class overrides the default sequence start and finish methods to
    write out the `useq.MDASequence` model and the collected frame-by-frame
    metadata to separate JSON files, providing a complete record of the
    acquisition.
    """

    def __init__(self, filename: str):
        # OMETiffWriter does not accept an overwrite argument; it always overwrites.
        super().__init__(filename)
        self._basename = Path(filename).with_suffix("").name

    def sequenceStarted(self, seq: MDASequence, meta: SummaryMetaV1 | object = object()):
        """
        Called when the sequence starts.

        This method creates the necessary output directory and saves the
        `MDASequence` object to a JSON file.
        """
        super().sequenceStarted(seq, meta)
        # Create directory for metadata if it doesn't exist
        self._meta_dir = Path(self._filename).parent
        self._meta_dir.mkdir(parents=True, exist_ok=True)

        # Save the main sequence metadata
        seq_path = self._meta_dir / f"{self._basename}_useq_MDASequence.json"
        seq_path.write_text(seq.model_dump_json(indent=2))

    def sequenceFinished(self, seq: MDASequence):
        """
        Called when the sequence is finished.

        This method saves all collected frame metadata to a JSON file.
        """
        super().sequenceFinished(seq)
        # Save the frame metadata
        if self.frame_metadatas:
            # The frame_metadatas in the base class is a dict mapping position keys
            # to lists of frame metadata dicts.
            serializable_meta = {
                pos_key: [to_builtins(m) for m in metas] for pos_key, metas in self.frame_metadatas.items()
            }
            meta_path = self._meta_dir / f"{self._basename}_frame_metadata.json"
            meta_path.write_text(json.dumps(serializable_meta, indent=2))
