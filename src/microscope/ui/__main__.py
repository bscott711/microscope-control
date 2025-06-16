import sys
from pathlib import Path

from pymmcore_plus import CMMCorePlus
from PySide6.QtWidgets import QApplication

from microscope.core.engine import AcquisitionEngine
from microscope.hardware.hal import HardwareAbstractionLayer
from microscope.ui.main_window import MainWindow


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)

    # 1. Create the core objects
    mmc = CMMCorePlus.instance()
    view = MainWindow()
    hal = HardwareAbstractionLayer(mmc)

    # FIX: Pass both the 'hal' (Model) and the 'view' (View)
    # to the 'engine' (Controller).
    engine = AcquisitionEngine(hal=hal, view=view)  # noqa: F841

    # 2. Handle Demo Mode vs. Real Hardware
    def load_config():
        is_demo = view.demo_mode_checkbox.isChecked()
        config_file = "demo.cfg" if is_demo else "20250523-OPM.cfg"

        # Assumes hardware_profiles is at the project root
        config_path = Path(__file__).resolve().parent.parent.parent.parent / "hardware_profiles" / config_file

        view.update_status(f"Loading config: {config_file}...")
        if config_path.exists():
            try:
                mmc.loadSystemConfiguration(str(config_path))
                view.update_status("Ready.")
                view.start_button.setEnabled(True)
            except Exception as e:
                view.update_status(f"Error loading {config_file}: {e}")
                view.start_button.setEnabled(False)
        else:
            view.update_status(f"Error: Config file not found at {config_path}")
            view.start_button.setEnabled(False)

    # Connect the checkbox to the loading function
    view.demo_mode_checkbox.stateChanged.connect(load_config)

    # Load the initial configuration
    load_config()

    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
