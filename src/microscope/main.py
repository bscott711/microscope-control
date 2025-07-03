# src/microscope/main.py

import sys

from pymmcore_gui import WidgetAction, create_mmgui
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication
from useq import MDASequence

from microscope.core.engine import CustomPLogicMDAEngine


def main():
    # DO NOT create the QApplication here.
    # Let create_mmgui create the proper MMQApplication to avoid the warning.
    window = create_mmgui(exec_app=False)
    mmc = CMMCorePlus.instance()

    # 1. Create and register your custom engine
    engine = CustomPLogicMDAEngine()
    mmc.register_mda_engine(engine)
    print("Custom PLogic MDA Engine registered.")

    # 2. Get the MDA widget from the GUI
    mda_widget = window.get_widget(WidgetAction.MDA_WIDGET)

    if mda_widget:
        # 3. Define a wrapper to bridge the mismatched signatures
        def mda_runner(output=None):
            sequence: MDASequence = mda_widget.value()
            engine.run(sequence)

        # 4. Assign the wrapper function to the widget's execute method
        mda_widget.execute_mda = mda_runner
        print("MDA 'Run' button has been wired to use CustomPLogicMDAEngine.")
    else:
        print("WARNING: Could not find MDA widget to intercept.")

    window.show()

    # Get the application instance that create_mmgui made and run it
    app = QApplication.instance()
    if app:
        sys.exit(app.exec_())


if __name__ == "__main__":
    main()
