# src/microscope/main.py

import sys

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication
from useq import MDASequence

# Import the functions and constants we need
from microscope.core.constants import HardwareConstants
from microscope.core.engine import CustomPLogicMDAEngine
from microscope.core.hardware import close_global_shutter, open_global_shutter


def main():
    """Launch the GUI, set up the engine, and manage hardware states."""
    # 1. Let create_mmgui create the correct MMQApplication instance.
    window = create_mmgui(exec_app=False)
    mmc = CMMCorePlus.instance()

    # 2. Now that the app exists, get a reference to it.
    app = QApplication.instance()
    if not app:
        print("FATAL: Could not get QApplication instance.", file=sys.stderr)
        return

    # 3. Set up hardware and engine
    HW = HardwareConstants()

    # Open the global shutter on startup
    print("Opening global shutter on startup...")
    open_global_shutter(mmc, HW)

    # Enable the SPIM beam on startup
    print("Enabling SPIM beam on startup...")
    mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "Yes")

    # Register the custom engine and intercept the MDA 'Run' button
    engine = CustomPLogicMDAEngine()
    mmc.register_mda_engine(engine)
    print("Custom PLogic MDA Engine registered.")

    mda_widget = window.get_widget(WidgetAction.MDA_WIDGET)
    if mda_widget:
        def mda_runner(output=None):
            """Wrapper to call our engine from the GUI."""
            sequence: MDASequence = mda_widget.value()
            engine.run(sequence)

        mda_widget.execute_mda = mda_runner
        print("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        print("WARNING: Could not find MDA widget to intercept.")

    # 4. Set up cleanup behavior
    def on_exit():
        """Clean up hardware state when the application quits."""
        print("Application closing. Disabling SPIM beam.")
        mmc.setProperty(HW.galvo_a_label, "BeamEnabled", "No")

        print("Closing global shutter.")
        close_global_shutter(mmc, HW)

    app.aboutToQuit.connect(on_exit)

    # 5. Show the window and start the application event loop
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
