import logging
import os
import sys
from pathlib import Path

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core import DeviceType  # Required for device type checking
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
    qInstallMessageHandler(qt_message_handler)
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(name)s: %(message)s")
    logger = logging.getLogger(__name__)

    app = QApplication(sys.argv)
    mmc = CMMCorePlus.instance()
    hal = HardwareAbstractionLayer(mmc)
    hw_constants = HardwareConstants()

    try:
        # --- Load Hardware Configuration ---
        is_demo = os.getenv("MICROSCOPE_DEMO", "").lower() in ("1", "true")
        config_name = "demo.cfg" if is_demo else "20250523-OPM.cfg"
        logger.info(f"Loading configuration: {config_name}")
        config_path = Path(__file__).parent.parent.parent.parent / "hardware_profiles"
        config_file = config_path / config_name
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
        mmc.loadSystemConfiguration(str(config_file))

        # --- Post-Load Hardware Stabilization ---
        # The PVCAM adapter may leave cameras in an unstable state after loading.
        # We explicitly set them to a stable internal trigger mode before creating
        # the UI to prevent crashes when UI elements query camera properties.
        logger.info("Stabilizing camera states...")
        for label in mmc.getLoadedDevices():
            if mmc.getDeviceType(label) == DeviceType.CameraDevice:
                if mmc.hasProperty(label, "TriggerMode"):
                    try:
                        allowed = mmc.getAllowedPropertyValues(label, "TriggerMode")
                        for mode in ["Internal Trigger", "Edge Trigger", "Level Trigger"]:
                            if mode in allowed:
                                mmc.setProperty(label, "TriggerMode", mode)
                                logger.info(f"Set '{label}' TriggerMode to '{mode}'")
                                break
                    except Exception as e:
                        logger.warning(f"Could not set TriggerMode for '{label}': {e}")

        logger.info("Discovering hardware devices...")
        hal._discover_devices()
        logger.info("Initialization complete.")

    except Exception as e:
        logger.critical(f"Could not initialize microscope: {e}", exc_info=True)
        sys.exit(1)

    # --- Create UI AFTER hardware is stabilized ---
    engine = AcquisitionEngine(hal=hal, hw_constants=hw_constants)
    win = MainWindow(engine)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
