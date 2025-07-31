# src/microscope/main.py

import logging
import sys
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import (
    ImageSequenceWriter,
    OMETiffWriter,
    OMEZarrWriter,
)
from qtpy.QtWidgets import QApplication
from useq import MDASequence

from microscope.core.constants import HardwareConstants
from microscope.core.engine import CustomPLogicMDAEngine
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
            plogic_device = mmc.getShutterDevice()
            plogic_state = mmc.getProperty(plogic_device, "OutputChannel")
            logger.info(f"Read PLogic state after disabling laser: {plogic_state}")

            logger.debug("Disabling SPIM beam after snap.")
            mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
            beam_state = mmc.getProperty(HW.galvo_a_label, "BeamEnabled")
            logger.info(f"Read beam state after disabling: {beam_state}")

            logger.debug("snap_cleanup: Disconnecting one-shot signal.")
            mmc.events.imageSnapped.disconnect(snap_cleanup)
            logger.info("Laser and beam disabled. Snap cleanup complete.")

        @wraps(original_snap_func)
        def snap_with_laser(*args, **kwargs):
            """Wrapper that enables beam, turns laser on, snaps, and schedules cleanup."""
            logger.info("Snap action triggered: entering laser/beam control wrapper.")

            logger.debug("Enabling SPIM beam for snap...")
            mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
            beam_state = mmc.getProperty(HW.galvo_a_label, "BeamEnabled")
            logger.info(f"Read beam state after enabling: {beam_state}")

            logger.debug("Enabling PLogic laser output for snap...")
            enable_live_laser(mmc, HW)
            plogic_device = mmc.getShutterDevice()
            plogic_state = mmc.getProperty(plogic_device, "OutputChannel")
            logger.info(f"Read PLogic state after enabling laser: {plogic_state}")

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
                plogic_device = mmc.getShutterDevice()
                plogic_state = mmc.getProperty(plogic_device, "OutputChannel")
                logger.info(f"Read PLogic state after disabling laser: {plogic_state}")

                logger.debug("Disabling SPIM beam after live mode...")
                mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
                beam_state = mmc.getProperty(HW.galvo_a_label, "BeamEnabled")
                logger.info(f"Read beam state after disabling: {beam_state}")

                logger.info("Live mode, laser, and beam disabled.")
            else:
                logger.debug("Live mode is OFF. Will be started.")

                logger.debug("Enabling SPIM beam for live mode...")
                mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")
                beam_state = mmc.getProperty(HW.galvo_a_label, "BeamEnabled")
                logger.info(f"Read beam state after enabling: {beam_state}")

                logger.debug("Enabling PLogic laser output for live mode...")
                enable_live_laser(mmc, HW)
                plogic_device = mmc.getShutterDevice()
                plogic_state = mmc.getProperty(plogic_device, "OutputChannel")
                logger.info(f"Read PLogic state after enabling laser: {plogic_state}")

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
        # This list will hold active context managers to prevent them from being
        # garbage collected before the acquisition is finished.
        _active_contexts = []

        def mda_runner(output=None):
            """Wrapper that gets sequence from GUI, creates a handler, and runs MDA."""
            from pymmcore_plus.mda import mda_listeners_connected

            sequence: MDASequence = mda_widget.value()
            save_info = mda_widget.save_info.value()

            handler = None
            if save_info["should_save"]:
                save_path = Path(save_info["save_dir"]) / save_info["save_name"]
                # NOTE: OMETiffWriter does not accept an overwrite argument.
                # OMEZarrWriter and ImageSequenceWriter do, but we let them default
                # to overwrite=False for safety. The user should manage the folder.
                if save_path.suffix in {".zarr", ".ome.zarr"}:
                    handler = OMEZarrWriter(save_path)
                elif save_path.suffix in {".tif", ".tiff", ".ome.tif", ".ome.tiff"}:
                    handler = OMETiffWriter(save_path)
                else:
                    handler = ImageSequenceWriter(save_path)

            if handler:
                # Create and enter the context manager, which starts the handler thread
                # and connects the signals.
                ctx = mda_listeners_connected(handler, mda_events=mmc.mda.events)
                _active_contexts.append(ctx)
                ctx.__enter__()

                # Define a one-shot function to exit the context and clean up
                # when the sequence is finished.
                def on_finish(sequence: MDASequence):
                    ctx.__exit__(None, None, None)
                    _active_contexts.remove(ctx)
                    mmc.mda.events.sequenceFinished.disconnect(on_finish)

                mmc.mda.events.sequenceFinished.connect(on_finish)

            # engine.run is non-blocking and will start the acquisition in a thread
            engine.run(sequence)

        # The pymmcore-gui MDAWidget is designed to be customized by replacing
        # the `execute_mda` method.
        mda_widget.execute_mda = mda_runner
        logger.info("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        logger.warning("Could not find MDA widget to intercept.")

    def on_exit():
        """Clean up hardware state when the application quits."""
        logger.info("Application closing. Ensuring SPIM beam is disabled.")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")
        beam_state = mmc.getProperty(HW.galvo_a_label, "BeamEnabled")
        logger.info(f"Final beam state: {beam_state}")

        logger.info("Closing global shutter.")
        close_global_shutter(mmc, HW)

        # Restore the original functions on exit
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
