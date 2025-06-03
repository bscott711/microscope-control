from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
)
from qtpy.QtGui import QDoubleValidator
from qtpy.QtCore import Qt

from ..hardware.stage import Stage # Assuming this path is correct for napari plugin structure


class StageControlWidget(QWidget):
    def __init__(self, viewer: "napari.viewer.Viewer"):
        super().__init__()
        self.viewer = viewer
        # Instantiate the stage, explicitly setting mock_hw=True by default
        # This allows the widget to run without actual hardware configuration.
        # For real hardware, Stage would need to be initialized with mock_hw=False
        # and correct configuration parameters.
        self.stage = Stage(mock_hw=True)
        self.setLayout(QVBoxLayout())

        # Step Size
        step_size_layout = QHBoxLayout()
        step_size_label = QLabel("Step Size (um):")
        self.step_size_input = QLineEdit("1.0")
        self.step_size_input.setValidator(QDoubleValidator(0.01, 10000.0, 2)) # Min, Max, Decimals
        step_size_layout.addWidget(step_size_label)
        step_size_layout.addWidget(self.step_size_input)
        self.layout().addLayout(step_size_layout)

        # Step Buttons
        step_buttons_layout = QHBoxLayout()
        self.step_forward_button = QPushButton("Step Forward")
        self.step_backward_button = QPushButton("Step Backward")
        step_buttons_layout.addWidget(self.step_backward_button)
        step_buttons_layout.addWidget(self.step_forward_button)
        self.layout().addLayout(step_buttons_layout)

        # Jog Speed
        jog_speed_layout = QHBoxLayout()
        jog_speed_label = QLabel("Jog Speed (um/s):")
        self.jog_speed_input = QLineEdit("10.0")
        self.jog_speed_input.setValidator(QDoubleValidator(0.1, 1000.0, 2)) # Min, Max, Decimals
        jog_speed_layout.addWidget(jog_speed_label)
        jog_speed_layout.addWidget(self.jog_speed_input)
        self.layout().addLayout(jog_speed_layout)

        # Jog Buttons
        jog_buttons_layout = QHBoxLayout()
        self.jog_forward_button = QPushButton("Jog Forward")
        self.jog_backward_button = QPushButton("Jog Backward")
        jog_buttons_layout.addWidget(self.jog_backward_button)
        jog_buttons_layout.addWidget(self.jog_forward_button)
        self.layout().addLayout(jog_buttons_layout)

        # Stop Jog Button
        self.stop_jog_button = QPushButton("Stop Jog")
        self.layout().addWidget(self.stop_jog_button)

        # Current Position
        current_pos_label_text = QLabel("Current Position (um):")
        self.current_position_display = QLabel("0.0")
        current_pos_layout = QHBoxLayout()
        current_pos_layout.addWidget(current_pos_label_text)
        current_pos_layout.addWidget(self.current_position_display)
        self.layout().addLayout(current_pos_layout)

        # Connect signals to slots
        self.step_forward_button.clicked.connect(self._on_step_forward)
        self.step_backward_button.clicked.connect(self._on_step_backward)
        self.jog_forward_button.clicked.connect(self._on_jog_forward)
        self.jog_backward_button.clicked.connect(self._on_jog_backward)
        self.stop_jog_button.clicked.connect(self._on_stop_jog)

        # Initialize position display
        self._update_position_display()

        # Add stretch to push elements to the top
        self.layout().addStretch()

    def _get_step_size(self) -> float:
        try:
            return float(self.step_size_input.text())
        except ValueError:
            print("Error: Invalid step size input. Please enter a number.")
            # Optionally, provide feedback to the user in the UI
            return 0.0 # Or raise an error, or return None

    def _get_jog_speed(self) -> float:
        try:
            return float(self.jog_speed_input.text())
        except ValueError:
            print("Error: Invalid jog speed input. Please enter a number.")
            # Optionally, provide feedback to the user in the UI
            return 0.0 # Or raise an error, or return None

    def _update_position_display(self):
        current_pos = self.stage.get_position()
        self.current_position_display.setText(f"{current_pos:.2f}")

    def _on_step_forward(self):
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop() # Stop any jogging before stepping
            print(f"UI: Step Forward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "forward")
            self._update_position_display()

    def _on_step_backward(self):
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop() # Stop any jogging before stepping
            print(f"UI: Step Backward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "backward")
            self._update_position_display()

    def _on_jog_forward(self):
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop() # Stop any previous jogging
            print(f"UI: Jog Forward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "forward")
            # Position display will update to current position before jog starts.
            # For continuous jogging, this would need a timer/thread to update.
            self._update_position_display()

    def _on_jog_backward(self):
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop() # Stop any previous jogging
            print(f"UI: Jog Backward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "backward")
            self._update_position_display()

    def _on_stop_jog(self):
        print("UI: Stop Jog clicked.")
        self.stage.stop()
        self._update_position_display()

if __name__ == "__main__":
    # For direct execution and testing of the widget
    # This requires the `hardware` module to be in the Python path.
    # You might need to adjust PYTHONPATH or run this from the project root directory.
    # Example: PYTHONPATH=$PYTHONPATH:/path/to/your/project python src/microscope_control/widgets/stage_control_widget.py
    import napari
    import sys
    import os
    # Add project root to sys.path for direct execution if needed
    # current_dir = os.path.dirname(os.path.abspath(__file__))
    # project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    # if project_root not in sys.path:
    #     sys.path.insert(0, project_root)
    # from microscope_control.hardware.stage import Stage # now this should work if path is set

    viewer = napari.Viewer()
    # If Stage is not found due to path issues for __main__,
    # you might need to mock it or ensure the path is correct.
    # For simplicity in this example, we assume 'from ..hardware.stage import Stage' works
    # if the script is run as part of a package or with PYTHONPATH set.
    # If running standalone and `..hardware` fails, change import to `from hardware.stage import Stage`
    # and ensure stage.py is in a subdir called 'hardware' relative to this script, or adjust sys.path.

    # Let's try to make the import more robust for standalone testing
    try:
        from ..hardware.stage import Stage
    except ImportError:
        # Fallback for direct script execution if run from within widgets dir
        # or if PYTHONPATH is not set up for src.microscope_control
        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        if module_path not in sys.path:
            sys.path.append(module_path)
        from hardware.stage import Stage


    widget = StageControlWidget(viewer)
    viewer.window.add_dock_widget(widget, area="right", name="Stage Control")

    viewer = napari.Viewer()
    # stage_instance = Stage() # Pass a real or mock stage if needed by widget's __init__ directly
    widget = StageControlWidget(viewer) # viewer is passed, stage is created within widget
    viewer.window.add_dock_widget(widget, area="right", name="Stage Control")
    napari.run()
