# src/microscope/controller/actions.py

import logging
import time
from typing import Callable, Optional

from pymmcore_gui.actions import core_actions

from microscope.core import disable_live_laser, enable_live_laser

logger = logging.getLogger(__name__)


class ActionsController:
    """
    Controller for single-shot actions like Snap and Live view.
    """

    def __init__(self, main_controller):
        self.mmc = main_controller.mmc
        self.hw = main_controller.hw
        self._original_snap_func: Optional[Callable] = None
        self._original_live_func: Optional[Callable] = None

    def connect_signals(self):
        """Wires up the snap and live GUI actions to their wrappers."""
        self._original_snap_func = core_actions.snap_action.on_triggered
        core_actions.snap_action.on_triggered = self._snap_with_laser

        self._original_live_func = core_actions.toggle_live_action.on_triggered
        core_actions.toggle_live_action.on_triggered = self._toggle_live_with_laser

    def _snap_with_laser(self, *args, **kwargs):
        """Wrapper for snap that enables beam, turns laser on, and schedules cleanup."""
        if not self._original_snap_func:
            return

        self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "Yes")
        enable_live_laser(self.mmc, self.hw)

        # Add a small delay to allow hardware to settle before snapping.
        time.sleep(0.1)

        self.mmc.events.imageSnapped.connect(self._snap_cleanup)
        self._original_snap_func(*args, **kwargs)

    def _snap_cleanup(self):
        """A one-shot callback to turn off the laser and beam after snap."""
        disable_live_laser(self.mmc, self.hw)
        self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "No")
        self.mmc.events.imageSnapped.disconnect(self._snap_cleanup)

    def _toggle_live_with_laser(self, *args, **kwargs):
        """Wrapper for live that adds laser and beam control."""
        if not self._original_live_func:
            return

        if self.mmc.isSequenceRunning():
            self._original_live_func(*args, **kwargs)
            disable_live_laser(self.mmc, self.hw)
            self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "No")
        else:
            self.mmc.setProperty(self.hw.galvo_a_label, "BeamEnabled", "Yes")
            enable_live_laser(self.mmc, self.hw)
            self._original_live_func(*args, **kwargs)

    def cleanup(self):
        """Restores original actions on application exit."""
        if self._original_snap_func:
            core_actions.snap_action.on_triggered = self._original_snap_func
        if self._original_live_func:
            core_actions.toggle_live_action.on_triggered = self._original_live_func
