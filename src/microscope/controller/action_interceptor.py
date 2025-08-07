"""
Intercepts and wraps core GUI actions with custom hardware logic.
"""

import logging

from pymmcore_gui.actions import core_actions
from pymmcore_plus import CMMCorePlus

from microscope.hardware import disable_live_laser, enable_live_laser
from microscope.model.hardware_model import HardwareConstants

logger = logging.getLogger(__name__)


class ActionInterceptor:
    """
    Holds custom hardware-aware functions and handles overriding the default
    pymmcore-gui actions.
    """

    def __init__(self, mmc: CMMCorePlus, model: HardwareConstants) -> None:
        self.mmc = mmc
        self.model = model
        # Store the original functions so we can restore them on exit.
        self._original_snap_func = core_actions.snap_action.on_triggered
        self._original_live_func = core_actions.toggle_live_action.on_triggered

    def override_actions(self) -> None:
        """Replace the default on_triggered callables with our custom ones."""
        core_actions.snap_action.on_triggered = self._custom_snap_func
        core_actions.toggle_live_action.on_triggered = self._custom_live_func
        logger.info("Snap and Live actions overridden with custom functions.")

    def _custom_snap_func(self, *args, **kwargs) -> None:
        """
        Hardware-aware snap function using an event-based cleanup to prevent
        race conditions.
        """
        logger.info("Custom snap function triggered.")

        def snap_cleanup() -> None:
            """A one-shot callback to turn off the laser after snap."""
            logger.debug("Snap cleanup: Disabling laser.")
            disable_live_laser(self.mmc, self.model)
            # Disconnect self to ensure this is a one-shot callback
            try:
                self.mmc.events.imageSnapped.disconnect(snap_cleanup)
                logger.debug("Snap cleanup callback disconnected.")
            except (TypeError, RuntimeError):
                pass  # May already be disconnected

        if self.mmc.isSequenceRunning():
            self.mmc.stopSequenceAcquisition()

        # Turn hardware ON
        enable_live_laser(self.mmc, self.model)

        # Connect the cleanup function to run once the snap is complete.
        self.mmc.events.imageSnapped.connect(snap_cleanup)
        # Call the original snap function
        if callable(self._original_snap_func):
            self._original_snap_func(*args, **kwargs)

    def _custom_live_func(self, *args, **kwargs) -> None:
        """Hardware-aware function for the live action."""
        logger.info("Custom live function triggered.")
        if not self.mmc.isSequenceRunning():
            logger.info("Starting live mode, enabling laser.")
            enable_live_laser(self.mmc, self.model)
            self.mmc.startContinuousSequenceAcquisition(0)
        else:
            logger.info("Stopping live mode, disabling laser.")
            self.mmc.stopSequenceAcquisition()
            disable_live_laser(self.mmc, self.model)

    def restore_actions(self) -> None:
        """Restore the original, unwrapped actions on application exit."""
        core_actions.snap_action.on_triggered = self._original_snap_func
        core_actions.toggle_live_action.on_triggered = self._original_live_func
        logger.info("Original snap/live functions have been restored.")
