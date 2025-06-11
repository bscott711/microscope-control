# src/microscope/live_engine.py
"""
Live Engine Module

This module contains the engine for handling live, interactive tasks such as
live camera view and continuous stage position polling. It runs in a separate
thread to avoid blocking the main GUI thread.
"""

import time

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

from .display import normalize_to_8bit  # <--- IMPORT THE NEW FUNCTION
from .hardware import HardwareController


class LiveEngine(QObject):
    """
    Engine for managing live view and navigation updates.

    Communicates with the GUI via signals for thread-safe updates.
    """

    # --- Signals ---
    new_live_image = Signal(np.ndarray)
    positions_updated = Signal(dict)
    stopped = Signal()

    def __init__(self, hw_controller: HardwareController):
        super().__init__()
        self.hw = hw_controller
        self._running = False
        self._live = False
        self._exposure_ms = 30.0

    @Slot()
    def run(self):
        """
        The main worker loop for the LiveEngine.

        This single loop handles both position polling and live view, switching
        based on the self._live flag. This avoids complex thread management for
        switching modes.
        """
        self._running = True
        print("Live Engine: Started.")

        while self._running:
            if self._live:
                # Live View Mode
                if (
                    self.hw.mmc.isSequenceRunning()
                    and self.hw.mmc.getRemainingImageCount() > 0
                ):
                    try:
                        tagged_img = self.hw.mmc.popNextTaggedImage()
                        img = tagged_img.pix.reshape(
                            self.hw.mmc.getImageHeight(),
                            self.hw.mmc.getImageWidth(),
                        )
                        # --- NORMALIZE IMAGE BEFORE EMITTING ---
                        image_8bit = normalize_to_8bit(img)
                        self.new_live_image.emit(image_8bit)
                        # ----------------------------------------
                    except IndexError:
                        # This can happen in a race condition where the buffer
                        # empties between our check and the popNextTaggedImage
                        # call. We just sleep briefly and continue.
                        time.sleep(0.005)
                else:
                    time.sleep(0.005)  # Prevent busy-waiting
            else:
                # Position Polling Mode
                positions = self.hw.get_all_positions()
                self.positions_updated.emit(positions)
                time.sleep(0.1)  # Poll at ~10 Hz

        print("Live Engine: Stopped.")
        self.stopped.emit()

    @Slot(float)
    def start_live_view(self, exposure_ms: float):
        """Switches the engine to live view mode."""
        if self._live:
            return
        self._exposure_ms = exposure_ms
        self.hw.start_live_scan(self._exposure_ms)
        self._live = True
        print(f"Live Engine: Switched to live view with {exposure_ms}ms exposure.")

    @Slot()
    def stop_live_view(self):
        """Switches the engine back to position polling mode."""
        if not self._live:
            return
        self.hw.stop_live_scan()
        self._live = False
        print("Live Engine: Switched to position polling.")

    @Slot()
    def stop(self):
        """Stops the main worker loop and cleans up."""
        if self._live:
            self.stop_live_view()
        self._running = False

    @Slot(str, float)
    def move_stage_to(self, axis_label: str, position: float):
        """Moves a stage to an absolute position."""
        self.hw.set_position(axis_label, position)

    @Slot(str, float)
    def move_stage_by(self, axis_label: str, offset: float):
        """Moves a stage by a relative offset."""
        self.hw.set_relative_position(axis_label, offset)

    @Slot(str, float)
    def start_jog(self, axis_label: str, speed: float):
        """Starts jogging a stage."""
        self.hw.start_jog(axis_label, speed)

    @Slot(str)
    def stop_jog(self, axis_label: str):
        """Stops jogging a stage."""
        self.hw.stop_jog(axis_label)

    @Slot()
    def stop_all_stages(self):
        """Stops all stage movement."""
        self.hw.stop_all_stages()
