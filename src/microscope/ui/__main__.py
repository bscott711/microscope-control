import sys

from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

from .main_window import MainWindow


def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)
    mmc = CMMCorePlus()
    try:
        # NOTE: For the Objective and Channel widgets to work, this config
        # file must contain "Objective" and "Channel" configuration groups.
        mmc.loadSystemConfiguration()  # Loads demo config by default
    except Exception as e:
        print(f"Could not load MM configuration: {e}")

    win = MainWindow(mmc)
    win.showMaximized()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
