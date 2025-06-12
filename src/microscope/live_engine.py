# src/microscope/live_engine.py
"""
Live Engine Module

This module handles live, interactive tasks and runs in a separate thread.
It now interacts directly with pymmcore-plus for all hardware communication.
"""

import time

import numpy as np
from pymmcore_plus import CMMCorePlus
from PySide6.QtCore import QObject, Signal, Slot

from .display import normalize_to_8bit
from .settings import HardwareConstants


class LiveEngine(QObject):
    """Engine for managing live view and navigation updates."""

    new_live_image = Signal(np.ndarray)
    positions_updated = Signal(dict)
    stopped = Signal()

    def __init__(self, mmc: CMMCorePlus, const: HardwareConstants):
        super().__init__()
        self.mmc = mmc
        self.const = const
        self._running = False
        self._live = False

    def _execute_tiger_serial_command(self, command: str):
        """Sends a raw serial command to the Tiger controller."""
        hub = self.const.TIGER_COMM_HUB_LABEL
        original_setting = self.mmc.getProperty(hub, "OnlySendSerialCommandOnChange")
        if original_setting == "Yes":
            self.mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "No")

        self.mmc.setProperty(hub, "SerialCommand", command)
        print(f"[SERIAL] Sending: {command}")

        if original_setting == "Yes":
            self.mmc.setProperty(hub, "OnlySendSerialCommandOnChange", "Yes")
        time.sleep(0.02)

    @Slot()
    def run(self):
        """The main worker loop for the LiveEngine."""
        self._running = True
        print("Live Engine: Started.")

        while self._running:
            if self._live:
                if self.mmc.isSequenceRunning() and self.mmc.getRemainingImageCount() > 0:
                    try:
                        tagged_img = self.mmc.popNextTaggedImage()
                        img = tagged_img.pix.reshape(self.mmc.getImageHeight(), self.mmc.getImageWidth())
                        self.new_live_image.emit(normalize_to_8bit(img))
                    except IndexError:
                        time.sleep(0.005)
                else:
                    time.sleep(0.005)
            else:
                # Position Polling Mode
                try:
                    positions = {
                        "XY-X": self.mmc.getXPosition(self.const.XY_STAGE_LABEL),
                        "XY-Y": self.mmc.getYPosition(self.const.XY_STAGE_LABEL),
                        "Z-Piezo": self.mmc.getPosition(self.const.Z_PIEZO_LABEL),
                        "Z-Stage": self.mmc.getPosition(self.const.Z_STAGE_LABEL),
                        "Filter-Z": self.mmc.getPosition(self.const.FILTER_Z_STAGE_LABEL),
                    }
                    self.positions_updated.emit(positions)
                except Exception as e:
                    print(f"Warning: Could not get stage positions: {e}")
                time.sleep(0.1)

        print("Live Engine: Stopped.")
        self.stopped.emit()

    @Slot(float)
    def start_live_view(self, exposure_ms: float):
        """Starts a continuous 'live' camera acquisition."""
        if self._live:
            return
        self.mmc.setExposure(exposure_ms)
        self.mmc.startContinuousSequenceAcquisition(0)
        self._live = True
        print(f"Live Engine: Switched to live view with {exposure_ms}ms exposure.")

    @Slot()
    def stop_live_view(self):
        """Stops the continuous 'live' camera acquisition."""
        if not self._live:
            return
        if self.mmc.isSequenceRunning():
            self.mmc.stopSequenceAcquisition()
        self._live = False
        print("Live Engine: Switched to position polling.")

    @Slot()
    def stop(self):
        """Stops the main worker loop and cleans up."""
        if self._live:
            self.stop_live_view()
        # Stop all stages to ensure a clean state after polling/jogging
        for device_label in [
            self.const.XY_STAGE_LABEL,
            self.const.Z_PIEZO_LABEL,
            self.const.Z_STAGE_LABEL,
            self.const.FILTER_Z_STAGE_LABEL,
        ]:
            if self.mmc.deviceBusy(device_label):
                self.mmc.stop(device_label)
        self._running = False

    @Slot(str, float)
    def move_stage_to(self, axis_label: str, position: float):
        """Moves a stage to an absolute position."""
        device_map = {
            "XY-X": lambda p: self.mmc.setXYPosition(p, self.mmc.getYPosition()),
            "XY-Y": lambda p: self.mmc.setXYPosition(self.mmc.getXPosition(), p),
            "Z-Stage": lambda p: self.mmc.setPosition(self.const.Z_STAGE_LABEL, p),
            "Z-Piezo": lambda p: self.mmc.setPosition(self.const.Z_PIEZO_LABEL, p),
            "Filter-Z": lambda p: self.mmc.setPosition(self.const.FILTER_Z_STAGE_LABEL, p),
        }
        if axis_label in device_map:
            device_map[axis_label](position)

    @Slot(str, float)
    def move_stage_by(self, axis_label: str, offset: float):
        """Moves a stage by a relative offset."""
        device_map = {
            "XY-X": lambda o: self.mmc.setRelativeXYPosition(o, 0),
            "XY-Y": lambda o: self.mmc.setRelativeXYPosition(0, o),
            "Z-Stage": lambda o: self.mmc.setRelativePosition(self.const.Z_STAGE_LABEL, o),
            "Z-Piezo": lambda o: self.mmc.setRelativePosition(self.const.Z_PIEZO_LABEL, o),
            "Filter-Z": lambda o: self.mmc.setRelativePosition(self.const.FILTER_Z_STAGE_LABEL, o),
        }
        if axis_label in device_map:
            device_map[axis_label](offset)

    @Slot(str, float)
    def start_jog(self, axis_label: str, speed: float):
        """Starts jogging a stage continuously using serial commands."""
        serial_axis_map = {"XY-X": "X", "XY-Y": "Y", "Z-Stage": "Z", "Filter-Z": "F"}
        axis = serial_axis_map.get(axis_label)
        if not axis:
            print(f"Warn: Jogging not supported for device '{axis_label}'.")
            return
        speed_mm_per_sec = speed / 1000.0
        self._execute_tiger_serial_command(f"J {axis}={speed_mm_per_sec}")

    @Slot(str)
    def stop_jog(self, axis_label: str):
        """Stops jogging a specific stage by halting that axis."""
        serial_axis_map = {"XY-X": "X", "XY-Y": "Y", "Z-Stage": "Z", "Filter-Z": "F"}
        axis = serial_axis_map.get(axis_label)
        if not axis:
            self._execute_tiger_serial_command("H")
            return
        self._execute_tiger_serial_command(f"/{axis}")
