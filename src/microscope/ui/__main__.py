import logging
import os
import sys
from pathlib import Path

from pymmcore_plus import CMMCorePlus
from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from qtpy.QtWidgets import QApplication

from microscope.config import HardwareConstants
from microscope.hardware.engine import AcquisitionEngine
from microscope.hardware.hal import HardwareAbstractionLayer
from microscope.ui.main_window import MainWindow


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
    # Setup logging and Qt message redirection
    qInstallMessageHandler(qt_message_handler)
    logging.basicConfig(
        stream=sys.stdout, level=logging.INFO, format="%(name)s: %(message)s"
    )
    logger = logging.getLogger(__name__)

    # Initialize Qt Application
    app = QApplication(sys.argv)

    # Initialize Micro-Manager Core
    mmc = CMMCorePlus.instance()
    hal = HardwareAbstractionLayer(mmc)
    hw_constants = HardwareConstants()

    try:
        # --- Load Hardware Configuration FIRST ---
        is_demo = os.getenv("MICROSCOPE_DEMO", "").lower() in ("1", "true")
        config_name = "demo.cfg" if is_demo else "20250523-OPM.cfg"
        logger.info(f"Loading configuration: {config_name}")

        config_path = (
            Path(__file__).parent.parent.parent.parent / "hardware_profiles"
        )
        config_file = config_path / config_name

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        mmc.loadSystemConfiguration(str(config_file))
        logger.info("Discovering hardware devices...")
        hal._discover_devices()
        logger.info("Initialization complete.")

    except Exception as e:
        logger.critical(f"Could not initialize microscope: {e}", exc_info=True)
        sys.exit(1)

    # --- Create UI AFTER hardware is initialized ---
    engine = AcquisitionEngine(hal=hal, hw_constants=hw_constants)
    win = MainWindow(engine)
    win.show()

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
