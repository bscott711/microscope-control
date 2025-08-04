# src/microscope/controller/action_interceptor.py
"""
Intercepts and wraps core GUI actions with custom hardware logic.

This module provides a dedicated class to "monkey-patch" core GUI actions
from pymmcore-gui, such as snapping an image or toggling live view. This
allows for the injection of hardware-specific commands (e.g., enabling a
laser or beam path) without modifying the core GUI library, effectively
decoupling the hardware control from the user interface logic.
"""

import logging
from functools import wraps
from typing import Callable, Optional

from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus

from microscope.hardware import disable_live_laser, enable_live_laser, set_property
from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


class ActionInterceptor:
    """
    A class that wraps core GUI actions with hardware control logic.

    This isolates the patching of GUI actions from the main application
    controller, making the logic easier to manage and test. It ensures that
    original actions can be restored, preventing memory leaks or unintended
    behavior on application shutdown.

    Attributes:
        mmc: The CMMCorePlus instance for hardware communication.
        model: The hardware constants data model.
    """

    def __init__(self, mmc: CMMCorePlus, model: HardwareConstants) -> None:
        self.mmc = mmc
        self.model = model
        self._original_snap_func: Optional[Callable] = None
        self._original_live_func: Optional[Callable] = None

    def wrap_snap_action(self) -> None:
        """
        Wrap the core snap action to control the laser and beam.

        This method enables the laser and beam before the snap and ensures
        they are disabled afterward by connecting to the `imageSnapped` signal.
        """
        self._original_snap_func = core_actions.snap_action.on_triggered
        if not callable(self._original_snap_func):
            logger.warning("Could not find original snap function to wrap.")
            return

        def snap_cleanup() -> None:
            """Disable laser and disconnect self after snap is complete."""
            disable_live_laser(self.mmc, self.model)
            self.mmc.events.imageSnapped.disconnect(snap_cleanup)
            logger.debug("Snap cleanup complete: Laser disabled.")

        @wraps(self._original_snap_func)
        def snap_with_laser(*args, **kwargs) -> None:
            """Enable laser, trigger snap, and schedule cleanup."""
            logger.info("Snap action triggered, enabling laser.")
            set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "Yes")
            enable_live_laser(self.mmc, self.model)
            self.mmc.events.imageSnapped.connect(snap_cleanup)

            # We can now safely ignore this type error, as we've confirmed
            # it is callable and have stored the original.
            self._original_snap_func(*args, **kwargs)  # type: ignore

        core_actions.snap_action.on_triggered = snap_with_laser
        logger.info("Snap action wrapped for hardware control.")

    def wrap_toggle_live_action(self) -> None:
        """Wrap the core toggle live action to control the laser and beam."""
        self._original_live_func = core_actions.toggle_live_action.on_triggered
        if not callable(self._original_live_func):
            logger.warning("Could not find original live function to wrap.")
            return

        @wraps(self._original_live_func)
        def toggle_live_with_laser(*args, **kwargs) -> None:
            """
            Enable/disable laser in sync with live mode.

            The order of operations is important:
            - When stopping: stop live first, then disable laser.
            - When starting: enable laser first, then start live.
            """
            # If a sequence is running, the user is about to stop it.
            if self.mmc.isSequenceRunning():
                logger.info("Stopping live mode, disabling laser.")
                self._original_live_func(*args, **kwargs)  # type: ignore
                disable_live_laser(self.mmc, self.model)
            else:
                logger.info("Starting live mode, enabling laser.")
                set_property(self.mmc, self.model.galvo_a_label, "BeamEnabled", "Yes")
                enable_live_laser(self.mmc, self.model)
                self._original_live_func(*args, **kwargs)  # type: ignore

        core_actions.toggle_live_action.on_triggered = toggle_live_with_laser
        logger.info("Live action wrapped for hardware control.")

    def restore_actions(self) -> None:
        """Restore the original, unwrapped actions on application exit."""
        if callable(self._original_snap_func):
            core_actions.snap_action.on_triggered = self._original_snap_func
            logger.info("Original snap action restored.")
        if callable(self._original_live_func):
            core_actions.toggle_live_action.on_triggered = self._original_live_func
            logger.info("Original live action restored.")
