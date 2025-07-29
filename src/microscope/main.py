# src/microscope/main.py

import logging
import sys
from functools import wraps
from typing import Callable, Optional, cast

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus

# Import OMETiffWriter
from pymmcore_plus.mda.handlers import ImageSequenceWriter, OMETiffWriter, OMEZarrWriter
from qtpy.QtWidgets import QApplication
from useq import MDASequence

from microscope.core.constants import HardwareConstants

# Import the protocol from engine.py
from microscope.core.engine import CustomPLogicMDAEngine, SupportsMDAEvents
from microscope.core.hardware import (
    close_global_shutter,
    disable_live_laser,
    enable_live_laser,
    open_global_shutter,
    set_camera_trigger_mode_level_high,
)

# Set up logger
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


def main():
    """Launch the GUI, set up the engine, and manage hardware states."""
    mmc = CMMCorePlus.instance()
    HW = HardwareConstants()

    # --- Inject Laser Control Logic ---

    # 1. Wrap the 'snap_image' function
    original_snap_func: Optional[Callable] = core_actions.snap_action.on_triggered
    if original_snap_func:

        def snap_cleanup():
            """A one-shot callback to turn off the laser and beam after snap."""
            logger.debug("snap_cleanup: Disabling PLogic laser output.")
            disable_live_laser(mmc, HW)
            logger.debug("snap_cleanup: Disconnecting one-shot signal.")
            mmc.events.imageSnapped.disconnect(snap_cleanup)
            logger.info("Laser and beam disabled. Snap cleanup complete.")

        @wraps(original_snap_func)
        def snap_with_laser(*args, **kwargs):
            """Wrapper that enables the beam, turns the laser on, snaps, and schedules cleanup."""
            logger.info("Snap action triggered: entering laser/beam control wrapper.")
            logger.debug("Enabling SPIM beam for snap...")
            mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
            logger.debug("Enabling PLogic laser output for snap...")
            enable_live_laser(mmc, HW)
            logger.debug("Connecting snap_cleanup to imageSnapped signal.")
            mmc.events.imageSnapped.connect(snap_cleanup)
            logger.debug("Calling original snap function...")
            original_snap_func(*args, **kwargs)

        core_actions.snap_action.on_triggered = snap_with_laser
        logger.info("Snap action wired for verbose laser and beam control.")

    # 2. Wrap the 'toggle_live' function
    original_live_func: Optional[Callable] = core_actions.toggle_live_action.on_triggered
    if original_live_func:

        @wraps(original_live_func)
        def toggle_live_with_laser(*args, **kwargs):
            """A wrapper for the live function that adds laser and beam control."""
            logger.info("Toggle live action triggered: entering laser/beam control wrapper.")
            if mmc.isSequenceRunning():
                logger.debug("Live mode is ON. Will be stopped.")
                original_live_func(*args, **kwargs)
                logger.debug("Disabling PLogic laser output after live mode...")
                disable_live_laser(mmc, HW)
                logger.info("Live mode and laser disabled.")
            else:
                logger.debug("Live mode is OFF. Will be started.")
                logger.debug("Enabling SPIM beam for live mode...")
                mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
                logger.debug("Enabling PLogic laser output for live mode...")
                enable_live_laser(mmc, HW)
                logger.debug("Starting live mode...")
                original_live_func(*args, **kwargs)
                logger.info("Live mode, laser, and beam enabled.")

        core_actions.toggle_live_action.on_triggered = toggle_live_with_laser
        logger.info("Live action wired for verbose laser and beam control.")

    # --- Application Setup ---

    window = create_mmgui(exec_app=False)

    app = QApplication.instance()
    if not app:
        logger.fatal("Could not get QApplication instance.")
        return

    logger.info("Opening global shutter on startup...")
    open_global_shutter(mmc, HW)

    # Set trigger modes for all cameras on startup
    logger.info("Setting camera trigger modes on startup...")
    set_camera_trigger_mode_level_high(mmc, HW)

    engine = CustomPLogicMDAEngine()
    mmc.register_mda_engine(engine)
    logger.info("Custom PLogic MDA Engine registered.")

    mda_widget = window.get_widget(WidgetAction.MDA_WIDGET)
    if mda_widget:

        def mda_runner(output=None):
            """Wrapper that creates a writer and passes it to our custom engine."""
            sequence: MDASequence = mda_widget.value()
            writer: Optional[SupportsMDAEvents] = None # Explicitly type the writer variable

            if output:
                save_path = output
                # Get format and overwrite settings using the widget's public API
                # Safer default handling using hasattr and explicit checks
                save_format = "ome-tiff" # Default changed to ome-tiff
                if hasattr(mda_widget, "save_format"):
                    save_format_callable = getattr(mda_widget, "save_format")
                    if callable(save_format_callable):
                         tmp_format = save_format_callable()
                         if isinstance(tmp_format, str): # Extra safety check
                            save_format = tmp_format

                overwrite = False # Default
                if hasattr(mda_widget, "overwrite"):
                    overwrite_callable = getattr(mda_widget, "overwrite")
                    if callable(overwrite_callable):
                        tmp_overwrite = overwrite_callable()
                        # Explicitly cast to bool to satisfy type checker
                        overwrite = bool(tmp_overwrite)

                logger.info(f"Saving is enabled. Format: {save_format}, Path: {save_path}")

                # Create the appropriate writer based on the format
                if save_format == "ome-zarr":
                    writer_instance = OMEZarrWriter(save_path, overwrite=overwrite)
                    # Cast the instance to the protocol type for type checker
                    writer = cast(SupportsMDAEvents, writer_instance)
                    logger.info("OME-Zarr writer created.")
                elif save_format == "ome-tiff":
                    # Use the specific OME-TIFF writer
                    writer_instance = OMETiffWriter(save_path)
                    # Cast the instance to the protocol type for type checker
                    writer = cast(SupportsMDAEvents, writer_instance)
                    logger.info("OME-TIFF writer created.")
                elif save_format == "tiff-sequence":
                     # Use ImageSequenceWriter for plain TIFF sequences if needed
                     writer_instance = ImageSequenceWriter(save_path, overwrite=overwrite)
                     # Cast the instance to the protocol type for type checker
                     writer = cast(SupportsMDAEvents, writer_instance)
                     logger.info("TIFF-Sequence writer created.")
                else:
                    logger.warning(f"Unknown save format '{save_format}'. No writer will be created.")

            # Pass the writer (or None) directly to the engine.
            # The engine's worker will connect its signals to the writer's methods.
            # No WriterAdapter needed.
            # Cast the writer again before passing to ensure type compatibility at call site
            engine.run(sequence, cast(Optional[SupportsMDAEvents], writer))

        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to support saving with CustomPLogicMDAEngine.")
    else:
        logger.warning("Could not find MDA widget to intercept.")

    def on_exit():
        """Clean up hardware state when the application quits."""
        logger.info("Application closing. Ensuring SPIM beam is disabled.")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
        logger.info("Closing global shutter.")
        close_global_shutter(mmc, HW)

        if original_snap_func:
            core_actions.snap_action.on_triggered = original_snap_func
        if original_live_func:
            core_actions.toggle_live_action.on_triggered = original_live_func
        logger.info("Original snap/live actions restored.")

    app.aboutToQuit.connect(on_exit)

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
