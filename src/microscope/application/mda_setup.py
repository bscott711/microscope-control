# src/microscope/application/mda_setup.py
"""
mda_setup.py
Responsible for wiring the MDA widget to the custom PLogic MDA engine.
This isolates the complex MDA setup logic from the main application controller.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMETiffWriter
from useq import MDAEvent, MDASequence

from microscope.acquisition import PLogicMDAEngine
from microscope.model.hardware_model import HardwareConstants

# Use TYPE_CHECKING to avoid circular import at runtime
if TYPE_CHECKING:
    from pymmcore_plus.mda.handlers import ImageSequenceWriter, OMEZarrWriter
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


class MultiCameraWriter:
    """An MDA handler that saves data from multiple cameras to separate files."""

    def __init__(self, base_path: Path, mmcore: CMMCorePlus):
        self._base_path = base_path
        self._mmc = mmcore
        self._writers: dict[str, OMETiffWriterWithMetadata] = {}
        self._camera_names: list[str] = []

    def sequenceStarted(self, seq: MDASequence, meta: Any = None) -> None:
        """
        Create a separate OMETiffWriter for each physical camera.
        """
        active_camera = self._mmc.getCameraDevice()
        if self._mmc.getDeviceLibrary(active_camera) == "Utilities":
            num_channels = self._mmc.getNumberOfCameraChannels()
            self._camera_names = [self._mmc.getCameraChannelName(i) for i in range(num_channels)]
        else:
            self._camera_names = [active_camera]

        logger.info(f"MultiCameraWriter started for cameras: {self._camera_names}")

        for cam_name in self._camera_names:
            p = self._base_path
            # Append camera name to the base filename
            cam_path = p.with_name(f"{p.stem}_{cam_name}{p.suffix}")
            self._writers[cam_name] = OMETiffWriterWithMetadata(str(cam_path))
            # Start each individual writer
            self._writers[cam_name].sequenceStarted(seq, meta)

    def frameReady(self, frame: Any, event: MDAEvent, meta: Any = None) -> None:
        """
        Route the incoming frame to the correct writer based on camera metadata.
        """
        camera_name = meta.get("Camera")
        # Changed to INFO to provide progress during acquisition
        logger.info(f"MultiCameraWriter received frame. Camera from metadata: {camera_name}")
        if camera_name in self._writers:
            self._writers[camera_name].frameReady(frame, event, meta)
        else:
            logger.warning(f"Received frame from unknown camera: {camera_name}")

    def sequenceFinished(self, seq: MDASequence) -> None:
        """
        Signal to all writers that the sequence is finished.
        """
        for writer in self._writers.values():
            writer.sequenceFinished(seq)
        logger.info("MultiCameraWriter finished.")


def setup_mda_widget(
    mda_widget: "MDAWidget",
    mmc: CMMCorePlus,
    hw: HardwareConstants,
    save_handler: Optional[Union[OMETiffWriter, "OMEZarrWriter", "ImageSequenceWriter"]] = None,
):
    """
    Wires the MDA widget to use the CustomPLogicMDAEngine.
    """
    engine = PLogicMDAEngine(mmc, hw)
    mmc.register_mda_engine(engine)
    logger.info("Custom PLogic MDA Engine registered.")

    def mda_runner(output=None):
        sequence: MDASequence = mda_widget.value()
        save_info = mda_widget.save_info.value()

        handler = save_handler
        if not handler and save_info["should_save"]:
            save_path = Path(save_info["save_dir"]) / save_info["save_name"]

            if save_path.suffix.lower() in {".tif", ".tiff", ".ome.tif", ".ome.tiff"}:
                handler = MultiCameraWriter(save_path, mmc)
            else:
                logger.warning(
                    f"Unsupported save format for multi-camera: {save_path.suffix}. Using default OMETiffWriter."
                )
                handler = OMETiffWriterWithMetadata(str(save_path))

        if handler:
            mmc.mda.events.sequenceStarted.connect(handler.sequenceStarted)
            mmc.mda.events.frameReady.connect(handler.frameReady)
            mmc.mda.events.sequenceFinished.connect(handler.sequenceFinished)

            def _disconnect():
                mmc.mda.events.sequenceStarted.disconnect(handler.sequenceStarted)
                mmc.mda.events.frameReady.disconnect(handler.frameReady)
                mmc.mda.events.sequenceFinished.disconnect(handler.sequenceFinished)
                mmc.mda.events.sequenceFinished.disconnect(_disconnect)

            mmc.mda.events.sequenceFinished.connect(_disconnect)

        engine.run(sequence)

    if hasattr(mda_widget, "execute_mda"):
        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        logger.error("MDA widget does not have 'execute_mda' attribute.")

    return engine
