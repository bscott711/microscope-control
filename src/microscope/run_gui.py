import sys
import os

# Ensure the package root is in PYTHONPATH if running script directly for development
# This allows `from microscope.hardware import HardwareInterface` to work
# when the package itself hasn't been installed with `pip install -e .` in the *current* venv
# (though it should have been by the setup step)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PACKAGE_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..")) # up two levels from src/microscope to project root
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from microscope.hardware import HardwareInterface
from pymmcore_gui.__main__ import main as run_pymmcore_gui
from pymmcore_plus import CMMCorePlus

# Configuration file path (relative to the project root)
# This should match a valid hardware profile for your setup
CONFIG_FILE = "hardware_profiles/20250523-OPM.cfg"

def launch_gui():
    print(f"Attempting to initialize hardware with config: {CONFIG_FILE}...")

    # Make sure the config file path is absolute or correctly relative to where HardwareInterface expects it
    # HardwareInterface already has logic to try and resolve relative paths.

    try:
        # Instantiate HardwareInterface to load the MM configuration
        # This uses the global CMMCorePlus.instance()
        hw_interface = HardwareInterface(config_path=CONFIG_FILE)
        print(f"HardwareInterface initialized. MMCorePlus instance: {CMMCorePlus.instance()}")
        print(f"Loaded devices: {CMMCorePlus.instance().getLoadedDevices()}")

        if not CMMCorePlus.instance().getLoadedDevices():
            print("ERROR: No devices were loaded by HardwareInterface. pymmcore-gui may not function correctly.")
            # Optionally, exit here or let pymmcore-gui try to handle it
            # sys.exit(1)
        else:
            print("Devices loaded successfully. Proceeding to launch pymmcore-gui.")

    except Exception as e:
        print(f"CRITICAL: Failed to initialize HardwareInterface: {e}")
        print("pymmcore-gui may not function correctly or may not launch.")
        # Optionally, exit here or let pymmcore-gui try to handle it
        # sys.exit(1)

    print("Launching pymmcore-gui...")
    # Run the pymmcore-gui main application
    # This should pick up the globally configured CMMCorePlus.instance()
    run_pymmcore_gui()
    print("pymmcore-gui finished.")

if __name__ == "__main__":
    launch_gui()
