# src/microscope/controller/action_interceptor.py
"""
Intercepts and wraps core GUI actions with custom hardware logic.
"""

import logging
from functools import wraps
from typing import Callable, Optional

from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus

from microscope.hardware import disable_live_laser, enable_live_laser
from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


class ActionInterceptor:
    """
    A class dedicated to wrapping core actions with hardware control logic.

    This isolates the complex monkey-patching of GUI actions from the main
    application controller.
    """

    def __init__(self, mmc: CMMCorePlus, model: HardwareConstants):
        self.mmc = mmc
        self.model = model
        self._original_snap_func: Optional[Callable] = None
        self._original_live_func: Optional[Callable] = None

    def wrap_snap_action(self) -> None:
        """Wrap the core snap action to control the laser and beam."""
        self._original_snap_func = core_actions.snap_action.on_triggered
        if not self._original_snap_func:
            logger.warning("Could not find original snap function to wrap.")
            return

        def snap_cleanup() -> None:
            """Disable laser and disconnect self after snap."""
            disable_live_laser(self.mmc, self.model)
            self.mmc.events.imageSnapped.disconnect(snap_cleanup)
            logger.info("Laser and beam disabled. Snap cleanup complete.")

        @wraps(self._original_snap_func)
        def snap_with_laser(*args, **kwargs) -> None:
            """Enable laser, snap, and schedule cleanup."""
            logger.info("Snap action triggered.")
            self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
            enable_live_laser(self.mmc, self.model)
            self.mmc.events.imageSnapped.connect(snap_cleanup)
            self._original_snap_func(*args, **kwargs)  # type: ignore

        core_actions.snap_action.on_triggered = snap_with_laser
        logger.info("Snap action wired for hardware control.")

    def wrap_toggle_live_action(self) -> None:
        """Wrap the core toggle live action to control the laser and beam."""
        self._original_live_func = core_actions.toggle_live_action.on_triggered
        if not self._original_live_func:
            logger.warning("Could not find original live function to wrap.")
            return

        @wraps(self._original_live_func)
        def toggle_live_with_laser(*args, **kwargs) -> None:
            """Enable/disable laser with live mode."""
            # if we are currently running, we are about to stop
            if self.mmc.isSequenceRunning():
                self._original_live_func(*args, **kwargs)  # type: ignore
                disable_live_laser(self.mmc, self.model)
                logger.info("Live mode, laser disabled.")
            else:
                self.mmc.setProperty(self.model.galvo_a_label, "BeamEnabled", "Yes")
                enable_live_laser(self.mmc, self.model)
                self._original_live_func(*args, **kwargs)  # type: ignore
                logger.info("Live mode and laser enabled.")

        core_actions.toggle_live_action.on_triggered = toggle_live_with_laser
        logger.info("Live action wired for hardware control.")

    def restore_actions(self) -> None:
        """Restore the original actions on application exit."""
        if self._original_snap_func:
            core_actions.snap_action.on_triggered = self._original_snap_func
            logger.info("Original snap action restored.")
        if self._original_live_func:
            core_actions.toggle_live_action.on_triggered = self._original_live_func
            logger.info("Original live action restored.")
