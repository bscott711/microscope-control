# Import the necessary packages
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_widgets import StageWidget
from qtpy.QtWidgets import QApplication, QVBoxLayout, QWidget


# Create a QWidget class named MyWidget
class MyWidget(QWidget):
    """A simple QWidget focusing on the StageWidget."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the widget and its components."""
        super().__init__(parent=parent)
        self.setWindowTitle("pymmcore-widgets StageWidget Demo")

        # Get the CMMCorePlus instance and load the demo configuration.
        core = CMMCorePlus.instance()
        core.loadSystemConfiguration()

        # --- Create a StageWidget instance ---
        stage_widget = StageWidget(device="XY")

        # --- Set up the main application layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(stage_widget)
        self.setLayout(main_layout)
        self.resize(400, 400)


# Create a QApplication and show MyWidget
if __name__ == "__main__":
    app = QApplication([])
    widget = MyWidget()
    widget.show()
    app.exec_()
