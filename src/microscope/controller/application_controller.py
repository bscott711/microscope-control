# microscope/controller/application_controller.py
"""
Main application controller for the microscope.
"""

import json
import logging
from functools import wraps
from pathlib import Path
from typing import Callable, Optional, Union

from pymmcore_gui import WidgetAction
from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMETiffWriter,
    OMEZarrWriter,
)
from pymmcore_plus.metadata import SummaryMetaV1, to_builtins
from useq import MDASequence

from microscope.controller.hardware_controller import (
    close_global_shutter,
    disable_live_laser,
    enable_live_laser,
    open_global_shutter,
    set_camera_trigger_mode_level_high,
)
from microscope.controller.mda_controller import CustomPLogicMDAEngine
from microscope.model.hardware_model import HardwareConstants

# Set up logger
logger = logging.getLogger(__name__)


class OMETiffWriterWithMetadata(OMETiffWriter):
    """
    Extends OMETiffWriter to save metadata JSON files alongside the OME-TIFF.
    """

    def __init__(self, filename: str):
        super().__init__(filename)
        self._basename = Path(filename).with_suffix("").name

    def sequenceStarted(self, seq: MDASequence, meta: SummaryMetaV1 | object = object()):
        super().sequenceStarted(seq, meta)
        self._meta_dir = Path(self._filename).parent
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        seq_path = self._meta_dir / f"{self._basename}_useq_MDASequence.json"
        seq_path.write_text(seq.model_dump_json(indent=2))

    def sequenceFinished(self, seq: MDASequence):
        super().sequenceFinished(seq)
        if self.frame_metadatas:
            serializable_meta = {
                pos_key: [to_builtins(m) for m in metas] for pos_key, metas in self.frame_metadatas.items()
            }
            meta_path = self._meta_dir / f"{self._basename}_frame_metadata.json"
            meta_path.write_text(json.dumps(serializable_meta, indent=2))


class ApplicationController:
    """
    The main controller for the microscope application.
    """

    def __init__(self):
        from microscope.view.main_view import MainView

        self.mmc = CMMCorePlus.instance()
        self.model = HardwareConstants()
        self.view = MainView()

        self._original_snap_func: Optional[Callable] = None
        self._original_live_func: Optional[Callable] = None

        self._setup_logic()

    def run(self):
        """Starts the application."""
        self.view.show()

    def _setup_logic(self):
        """Wire up all the application logic."""
        self._disconnect_faulty_snap_handler()
        self._wrap_snap_action()
        self._wrap_toggle_live_action()

        open_global_shutter(self.mmc, self.model)
        set_camera_trigger_mode_level_high(self.mmc, self.model)

        engine = CustomPLogicMDAEngine()
        self.mmc.register_mda_engine(engine)
        logger.info("Custom PLogic MDA Engine registered.")

        self._wire_mda_widget(engine)

        if app := self.view.app():
            app.aboutToQuit.connect(self._on_exit)

    def _disconnect_faulty_snap_handler(self):
        """
        Disconnect the default snap handler in the viewers manager to prevent
        the race condition that causes a "Camera image buffer read failed" error.
        We will manually update the preview in our wrapped snap action.
        """
        try:
            manager = self.view.window._viewers_manager
            self.mmc.events.imageSnapped.disconnect(manager._on_image_snapped)
            logger.info("Successfully disconnected NDVViewersManager snap handler.")
        except Exception as e:
            logger.error("Failed to disconnect faulty snap handler: %s", e)

    def _wrap_snap_action(self):
        """
        Injects laser/beam control and a safe image preview update into the
        pymmcore-gui snap action.
        """
        self._original_snap_func = core_actions.snap_action.on_triggered
        if self._original_snap_func:

            @wraps(self._original_snap_func)
            def snap_with_laser(*args, **kwargs):
                assert self._original_snap_func is not None
                logger.info("Snap action triggered: entering synchronous laser/beam control.")

                self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
                enable_live_laser(self.mmc, self.model)

                try:
                    # This call is blocking and will not return until the snap is complete.
                    self._original_snap_func(*args, **kwargs)

                    # After the snap call is complete, it is safe to get the image.
                    logger.info("Snap finished, updating preview.")
                    last_image = self.mmc.getImage()

                    # Manually update the preview widget with the new image.
                    manager = self.view.window._viewers_manager
                    preview_widget = manager._create_or_show_img_preview()
                    if preview_widget:
                        preview_widget.append(last_image)

                except RuntimeError as e:
                    logger.error("Failed to get image after snap: %s", e)
                finally:
                    # This code is guaranteed to run after the snap is complete.
                    disable_live_laser(self.mmc, self.model)
                    self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "No")
                    logger.info("Laser and beam disabled. Snap cleanup complete.")

            core_actions.snap_action.on_triggered = snap_with_laser
            logger.info("Snap action wired for safe preview update and laser control.")

    def _wrap_toggle_live_action(self):
        """Injects laser/beam control into the pymmcore-gui toggle live action."""
        self._original_live_func = core_actions.toggle_live_action.on_triggered
        if self._original_live_func:

            @wraps(self._original_live_func)
            def toggle_live_with_laser(*args, **kwargs):
                assert self._original_live_func is not None
                if self.mmc.isSequenceRunning():
                    self._original_live_func(*args, **kwargs)
                    disable_live_laser(self.mmc, self.model)
                    self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "No")
                    logger.info("Live mode, laser, and beam disabled.")
                else:
                    self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
                    enable_live_laser(self.mmc, self.model)
                    self._original_live_func(*args, **kwargs)
                    logger.info("Live mode, laser, and beam enabled.")

            core_actions.toggle_live_action.on_triggered = toggle_live_with_laser
            logger.info("Live action wired for verbose laser and beam control.")

    def _wire_mda_widget(self, engine: CustomPLogicMDAEngine):
        """Connects the MDA 'Run' button to our custom engine."""
        mda_widget = self.view.get_widget(WidgetAction.MDA_WIDGET)
        if not mda_widget:
            logger.warning("Could not find MDA widget to intercept.")
            return

        _handler_manager = None

        def mda_runner(output=None):
            nonlocal _handler_manager
            sequence: MDASequence = mda_widget.value()
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
            _handler_manager = self.HandlerManager(self.mmc, handler)
            engine.run(sequence)

        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")

    def _on_exit(self):
        """Clean up hardware state and event connections when the application quits."""
        logger.info("Application closing. Cleaning up hardware.")
        self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "No")
        close_global_shutter(self.mmc, self.model)
        if self._original_snap_func:
            core_actions.snap_action.on_triggered = self._original_snap_func
        if self._original_live_func:
            core_actions.toggle_live_action.on_triggered = self._original_live_func
        logger.info("Original snap/live actions restored. Cleanup complete.")

    class HandlerManager:
        def __init__(
            self,
            mmc: CMMCorePlus,
            handler: Optional[Union[OMEZarrWriter, OMETiffWriterWithMetadata, ImageSequenceWriter]],
        ):
            self.mmc = mmc
            self.handler = handler
            if self.handler:
                mmc.mda.events.sequenceStarted.connect(self.handler.sequenceStarted)
                mmc.mda.events.frameReady.connect(self.handler.frameReady)
                mmc.mda.events.sequenceFinished.connect(self.handler.sequenceFinished)
            mmc.mda.events.sequenceFinished.connect(self._disconnect)

        def _disconnect(self, sequence: MDASequence):
            if self.handler:
                self.mmc.mda.events.sequenceStarted.disconnect(self.handler.sequenceStarted)
                self.mmc.mda.events.frameReady.disconnect(self.handler.frameReady)
                self.mmc.mda.events.sequenceFinished.disconnect(self.handler.sequenceFinished)
            self.mmc.mda.events.sequenceFinished.disconnect(self._disconnect)
