# src/microscope/__main__.py
"""
Main application launch script for the Microscope Control package.

This script sets up the Qt Application and initializes the main window. It is
designed to be executed when the package is run as a script.
"""

import sys
import os

from PySide6.QtCore import QObject, QThread, Slot
from PySide6.QtWidgets import QApplication

from pymmcore_plus import CMMCorePlus, find_micromanager

from .engine import AcquisitionEngine
from .hardware import HardwareController
from .settings import AcquisitionSettings, HardwareConstants


class TestRunner(QObject):
    """A simple class to run the engine and report results."""

    # --- Type Hints for Instance Attributes ---
    _worker_thread: QThread
    engine: AcquisitionEngine

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app

        # 1. Initialize Core Components
        self.mmc = CMMCorePlus.instance()
        self.const = HardwareConstants()
        try:
            # Find the path where `mmcore install` placed the device adapters
            mm_path = find_micromanager()
            if not mm_path:
                raise RuntimeError(
                    "Could not find Micro-Manager installation. "
                    "Please run 'mmcore install' first."
                )
            print(f"Found Micro-Manager at: {mm_path}")
            # Tell pymmcore where to look for device adapters
            self.mmc.setDeviceAdapterSearchPaths([mm_path])

            # Load Demo Devices for testing...
            print("Loading Demo Devices for testing...")

            # Define a list of devices to load. This makes management easier.
            devices_to_load = [
                ("Camera-1", "DemoCamera", "DCam"),
                ("Scanner:AB:33", "Utilities", "State Device Shutter"),
                ("PiezoStage:P:34", "Utilities", "State Device Shutter"),
                ("PLogic:E:36", "Utilities", "State Device Shutter"),
                ("TigerCommHub", "Utilities", "Serial port DTR Shutter"),
            ]

            # Load all devices from the list
            for label, library, name in devices_to_load:
                self.mmc.loadDevice(label, library, name)

            # Initialize ONLY the devices we just loaded, not the Core itself.
            for label, _, _ in devices_to_load:
                self.mmc.initializeDevice(label)

            self.mmc.setCameraDevice("Camera-1")

        except Exception as e:
            print(f"CRITICAL: Failed to load system configuration: {e}")
            self.app.quit()
            return

        self.hw = HardwareController(self.mmc, self.const)

        # 2. Define a Test Acquisition
        self.settings = AcquisitionSettings(
            num_slices=5,
            time_points=2,
            time_interval_s=2.0,
            is_minimal_interval=False,
        )

        # 3. Setup Engine in a Separate Thread
        self._worker_thread = QThread()
        self.engine = AcquisitionEngine(self.hw, self.settings)
        self.engine.moveToThread(self._worker_thread)

        # 4. Connect Signals and Slots
        self._worker_thread.started.connect(self.engine.run_acquisition)
        self.engine.acquisition_finished.connect(self.on_acquisition_finished)
        self.engine.status_updated.connect(lambda s: print(f"STATUS: {s}"))
        self.engine.new_image_ready.connect(
            lambda img: print(f"  Got image with shape {img.shape}")
        )

        print("--- Starting Acquisition Engine Test ---")
        self._worker_thread.start()

    @Slot()
    def on_acquisition_finished(self):
        """Safely quits the application when the engine is done."""
        print("--- Test Finished ---")
        self._worker_thread.quit()
        self._worker_thread.wait()
        self.app.quit()


def main():
    """Initializes and runs the Qt application."""
    app = QApplication(sys.argv)
    # FIX: Assign the TestRunner to a variable to prevent it from being
    # garbage collected prematurely, which would cause the QThread to be
    # destroyed while running.
    runner = TestRunner(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
