# src/microscope/ui/__main__.py

import logging
import os
import sys
from pathlib import Path

# Import your application components after
from pymmcore_plus import CMMCorePlus

# No need to set environment variables, as the test script proved it's not needed.
# Import Qt and superqt first
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from qtpy.QtWidgets import QApplication
from superqt import QIconifyIcon

from microscope.config import HardwareConstants
from microscope.hardware.engine import AcquisitionEngine
from microscope.hardware.hal import HardwareAbstractionLayer
from microscope.ui.main_window import MainWindow, QtLogHandler


def qt_message_handler(mode: QtMsgType, context, message: str):
    """Redirect Qt log messages to the Python logging module."""
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.CRITICAL,
        QtMsgType.QtFatalMsg: logging.FATAL,
    }
    level = levels.get(mode, logging.INFO)
    logger = logging.getLogger("Qt")
    logger.log(level, message)


def main():
    """Main application entry point."""
    qInstallMessageHandler(qt_message_handler)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(name)s: %(message)s")

    app = QApplication(sys.argv)

    # FIX: "Prime" the icon system before initializing anything else.
    # This forces the 'mdi' plugin to load early and without interference.
    # We don't need to do anything with the icon; just creating it is enough.
    try:
        _ = QIconifyIcon("mdi:home")
        print("INFO: Icon system initialized successfully.")
    except Exception as e:
        print(f"WARNING: Could not prime icon system: {e}")

    # Now proceed with the rest of the application setup
    mmc = CMMCorePlus.instance()
    mmc.unloadAllDevices()

    hal = HardwareAbstractionLayer(mmc)
    hw_constants = HardwareConstants()
    engine = AcquisitionEngine(hal=hal, hw_constants=hw_constants)
    win = MainWindow(engine)

    log_handler = QtLogHandler()
    sys.stdout = log_handler
    sys.stderr = log_handler
    log_handler.new_text.connect(win.log_widget.appendPlainText)

    win.show()

    try:
        config_name = "demo.cfg" if os.getenv("MICROSCOPE_DEMO") else "20250523-OPM.cfg"
        print(f"INFO: Loading configuration: {config_name}")

        config_path = Path(__file__).parent.parent.parent.parent / "hardware_profiles"
        config_file = config_path / config_name

        mmc.unloadAllDevices()
        mmc.loadSystemConfiguration(str(config_file))

        print("INFO: Discovering hardware devices...")
        hal._discover_devices()

        print("INFO: Setting up device-specific widgets...")
        win.setup_device_widgets()
        print("INFO: Initialization complete.")

    except Exception as e:
        print(f"FATAL: Could not initialize microscope. Error: {e}")
        import traceback

        traceback.print_exc()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
