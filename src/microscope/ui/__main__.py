import sys
from pathlib import Path


def find_project_root() -> Path:
    """Find the project root by searching upwards for `pyproject.toml`."""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("Could not find project root containing 'pyproject.toml'.")


def main():
    """Main function to run the application."""

    from pymmcore_plus import CMMCorePlus
    from qtpy.QtWidgets import QApplication

    # Correctly import the INSTANCE from the config module
    from ..config import hw_constants
    from ..hardware.engine import AcquisitionEngine
    from ..hardware.hal import HardwareAbstractionLayer
    from .main_window import MainWindow

    app = QApplication(sys.argv)
    project_root = find_project_root()

    # 1. Create the core objects
    mmc = CMMCorePlus.instance()
    hal = HardwareAbstractionLayer(mmc)

    # Correctly pass the INSTANCE to the engine
    engine = AcquisitionEngine(hal=hal, hw_constants=hw_constants)
    view = MainWindow(engine=engine)

    # 2. Handle Demo Mode vs. Real Hardware
    def load_config():
        is_demo = view.demo_mode_checkbox.isChecked()
        config_file = "demo.cfg" if is_demo else hw_constants.cfg_path

        config_path = project_root / "hardware_profiles" / config_file
        view.update_status(f"Loading config: {config_file}...")
        if config_path.exists():
            try:
                mmc.loadSystemConfiguration(str(config_path))
                view.update_status("Ready.")
                view.setup_device_widgets()
                view.mda_widget.run_button.setEnabled(True)
            except Exception as e:
                view.update_status(f"Error loading {config_file}: {e}")
                if hasattr(view, "mda_widget"):
                    view.mda_widget.run_button.setEnabled(False)
        else:
            view.update_status(f"Error: Config file not found at {config_path}")

    view.demo_mode_checkbox.stateChanged.connect(load_config)
    load_config()

    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
