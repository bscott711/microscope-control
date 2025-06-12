# microscope/__main__.py
import sys
import traceback

from PySide6.QtWidgets import QApplication

from .config import HW
from .gui import AcquisitionGUI
from .hardware_control import HardwareInterface, mmc


def main():
    """Main function to run the application."""
    # CORRECTED: Use the singleton pattern to get the existing QApplication
    # instance or create a new one if it doesn't exist. This prevents a
    # RuntimeError when a library like magicgui creates an instance for us.
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    try:
        hw_interface = HardwareInterface(config_file_path=HW.cfg_path)
        window = AcquisitionGUI(hw_interface)
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"An unexpected error occurred in __main__: {e}")
        traceback.print_exc()
    finally:
        if "mmc" in locals() and mmc.getLoadedDevices():
            mmc.reset()
        print("Script execution finished.")


if __name__ == "__main__":
    main()
