import sys
from pathlib import Path

# These are safe to import here as they are standard libraries
# and have no side effects like printing to the console.
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

# We import MainWindow and the LogHandler from the sub-module.
# Note: At this point, no actual code from these modules has been run.
from .main_window import MainWindow, QtLogHandler


def find_project_root() -> Path:
    """Find the project root by searching upwards for `pyproject.toml`."""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("Could not find project root containing 'pyproject.toml'.")


def main():
    """Main function to run the application."""
    app = QApplication(sys.argv)
    project_root = find_project_root()

    # --- Fix 1: Redirect stdout/stderr BEFORE creating the engine ---
    # Create the log handler instance directly.
    log_handler = QtLogHandler()
    sys.stdout = log_handler
    sys.stderr = log_handler

    # --- Now, perform the rest of the imports and initialization ---
    # This import will now correctly print its "demo mode" message to the log handler.
    from ..config import hw_constants
    from ..hardware.engine import AcquisitionEngine
    from ..hardware.hal import HardwareAbstractionLayer

    # 1. Create the core objects
    mmc = CMMCorePlus.instance()
    hal = HardwareAbstractionLayer(mmc)
    engine = AcquisitionEngine(hal=hal, hw_constants=hw_constants)

    # 2. Create the main window and connect the log handler's signal
    view = MainWindow(engine=engine)
    log_handler.new_text.connect(view.log_widget.appendPlainText)

    # 3. Handle Demo Mode vs. Real Hardware
    def load_config():
        is_demo = view.demo_mode_checkbox.isChecked()
        config_file = "hardware_profiles/demo.cfg" if is_demo else hw_constants.cfg_path

        # The path construction remains as you specified.
        config_path = project_root / config_file

        view.update_status(f"Loading config: {config_file}...")
        if config_path.exists():
            try:
                mmc.loadSystemConfiguration(str(config_path))
                view.update_status("Ready.")
                view.setup_device_widgets()
                view.mda_widget.run_button.setEnabled(True)
            except Exception as e:
                # This will now catch errors from within the config file itself
                view.update_status(f"Error loading {config_file}: {e}")
                if hasattr(view, "mda_widget"):
                    view.mda_widget.run_button.setEnabled(False)
        else:
            # --- Fix 2: Improved error message ---
            # This provides better debugging information if the path fails.
            msg = f"Config file not found! Searched at: {config_path}. (Project root detected at: {project_root})"
            view.update_status(msg)

    view.demo_mode_checkbox.stateChanged.connect(load_config)
    load_config()

    view.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
