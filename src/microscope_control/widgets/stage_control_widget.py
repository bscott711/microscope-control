from qtpy.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QLineEdit,
    # QDoubleValidator, # Removed from here
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QApplication, # Added QApplication
)
from qtpy.QtGui import QDoubleValidator
from qtpy.QtCore import Qt

from ..hardware.stage import Stage # Assuming this path is correct for napari plugin structure


class StageControlWidget(QWidget):
    def __init__(self, viewer: "napari.viewer.Viewer"):
        super().__init__()
        self.viewer = viewer
        self.stage = None # Stage instance will be created on initialization

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- Configuration Group ---
        config_group = QGroupBox("Configuration")
        config_layout = QFormLayout()
        config_group.setLayout(config_layout)

        self.mm_config_file_input = QLineEdit("hardware_profiles/20250523-OPM.cfg") # Updated default text
        self.stage_device_label_input = QLineEdit("ASI XYStage")
        self.mock_hw_checkbox = QCheckBox("Use Mock Hardware")
        self.mock_hw_checkbox.setChecked(True)

        self.initialize_button = QPushButton("Initialize Stage")
        self.disconnect_button = QPushButton("Disconnect Stage")
        self.disconnect_button.setEnabled(False)

        self.status_label = QLabel("Status: Not Initialized")
        self.status_label.setWordWrap(True)

        config_layout.addRow("MM Config File:", self.mm_config_file_input)
        config_layout.addRow("Stage Device Label:", self.stage_device_label_input)
        config_layout.addRow(self.mock_hw_checkbox)

        init_buttons_layout = QHBoxLayout()
        init_buttons_layout.addWidget(self.initialize_button)
        init_buttons_layout.addWidget(self.disconnect_button)
        config_layout.addRow(init_buttons_layout)
        config_layout.addRow(self.status_label)

        main_layout.addWidget(config_group)

        # --- Movement Controls Group ---
        self.movement_controls_group = QGroupBox("Movement Controls")
        movement_v_layout = QVBoxLayout()
        self.movement_controls_group.setLayout(movement_v_layout)

        step_size_form_layout = QFormLayout()
        self.step_size_input = QLineEdit("1.0")
        self.step_size_input.setValidator(QDoubleValidator(0.01, 10000.0, 2))
        step_size_form_layout.addRow("Step Size (um):", self.step_size_input)
        movement_v_layout.addLayout(step_size_form_layout)

        step_buttons_layout = QHBoxLayout()
        self.step_forward_button = QPushButton("Step Forward")
        self.step_backward_button = QPushButton("Step Backward")
        step_buttons_layout.addWidget(self.step_backward_button)
        step_buttons_layout.addWidget(self.step_forward_button)
        movement_v_layout.addLayout(step_buttons_layout)

        jog_speed_form_layout = QFormLayout()
        self.jog_speed_input = QLineEdit("10.0")
        self.jog_speed_input.setValidator(QDoubleValidator(0.1, 1000.0, 2))
        jog_speed_form_layout.addRow("Jog Speed (um/s):", self.jog_speed_input)
        movement_v_layout.addLayout(jog_speed_form_layout)

        jog_buttons_layout = QHBoxLayout()
        self.jog_forward_button = QPushButton("Jog Forward")
        self.jog_backward_button = QPushButton("Jog Backward")
        jog_buttons_layout.addWidget(self.jog_backward_button)
        jog_buttons_layout.addWidget(self.jog_forward_button)
        movement_v_layout.addLayout(jog_buttons_layout)

        self.stop_jog_button = QPushButton("Stop Jog")
        movement_v_layout.addWidget(self.stop_jog_button, alignment=Qt.AlignCenter)

        current_pos_layout = QHBoxLayout()
        current_pos_label_text = QLabel("Current Position (um):")
        self.current_position_display = QLabel("-")
        current_pos_layout.addWidget(current_pos_label_text)
        current_pos_layout.addWidget(self.current_position_display)
        movement_v_layout.addLayout(current_pos_layout)

        movement_v_layout.addStretch()

        self.movement_controls_group.setEnabled(False)
        main_layout.addWidget(self.movement_controls_group)
        main_layout.addStretch()

        # Connect signals to slots
        self.initialize_button.clicked.connect(self._on_initialize_stage)
        self.disconnect_button.clicked.connect(self._on_disconnect_stage)
        self.mock_hw_checkbox.stateChanged.connect(self._on_mock_hw_changed)

        self.step_forward_button.clicked.connect(self._on_step_forward)
        self.step_backward_button.clicked.connect(self._on_step_backward)
        self.jog_forward_button.clicked.connect(self._on_jog_forward)
        self.jog_backward_button.clicked.connect(self._on_jog_backward)
        self.stop_jog_button.clicked.connect(self._on_stop_jog)

        self._on_mock_hw_changed(self.mock_hw_checkbox.checkState()) # Set initial UI based on checkbox

    def _on_initialize_stage(self):
        if self.stage: # If already initialized, disconnect first to ensure clean state
            self._on_disconnect_stage()

        mm_config = self.mm_config_file_input.text()
        device_label = self.stage_device_label_input.text()
        use_mock = self.mock_hw_checkbox.isChecked()

        if not use_mock and (not mm_config or not device_label):
            self.status_label.setText("Status: Error - Config file and device label are required for real hardware.")
            return

        try:
            self.status_label.setText(f"Status: Initializing {'mock' if use_mock else device_label}...")
            QApplication.processEvents() # Allow UI to update status message

            self.stage = Stage(
                mm_config_file=mm_config,
                stage_device_label=device_label,
                mock_hw=use_mock
            )

            # If Stage initialization failed and it fell back to mock_hw=True internally
            if self.stage.mock_hw and not use_mock:
                 self.status_label.setText(f"Status: Error - Real HW init failed. Using mock stage for '{device_label}'.")
                 self.mock_hw_checkbox.setChecked(True) # Reflect fallback in UI
            else: # Success or intended mock initialization
                status_msg = "Status: Initialized "
                if self.stage.mock_hw:
                    status_msg += f"(Mock: {device_label})"
                else:
                    status_msg += f"(Real HW: {device_label})"
                self.status_label.setText(status_msg)

            self.movement_controls_group.setEnabled(True)
            self.disconnect_button.setEnabled(True)
            self.initialize_button.setEnabled(False)
            self.mm_config_file_input.setEnabled(False)
            self.stage_device_label_input.setEnabled(False)
            self.mock_hw_checkbox.setEnabled(False)
            self._update_position_display()

        except RuntimeError as e: # Catch errors from Stage init (e.g., pymmcore issues)
            self.stage = None # Ensure stage is None on failure
            self.status_label.setText(f"Status: Error - {e}")
            self.movement_controls_group.setEnabled(False)
            self.disconnect_button.setEnabled(False)
            self.initialize_button.setEnabled(True)
            # Re-enable config inputs based on mock_hw checkbox state
            self.mock_hw_checkbox.setEnabled(True)
            self._on_mock_hw_changed(self.mock_hw_checkbox.checkState())
            self._update_position_display() # Reset position text to "-"
        except Exception as e: # Catch any other unexpected error
            self.stage = None
            self.status_label.setText(f"Status: Unexpected error - {e}")
            self.movement_controls_group.setEnabled(False)
            self.disconnect_button.setEnabled(False)
            self.initialize_button.setEnabled(True)
            self.mock_hw_checkbox.setEnabled(True)
            self._on_mock_hw_changed(self.mock_hw_checkbox.checkState())
            self._update_position_display()


    def _on_disconnect_stage(self):
        if self.stage:
            # Currently, Stage class doesn't have an explicit disconnect/cleanup method.
            # If it did (e.g., self.stage.cleanup()), it would be called here.
            print(f"Disconnecting stage: {self.stage.stage_device_label if self.stage.stage_device_label else 'N/A'}")

        self.stage = None
        self.status_label.setText("Status: Not Initialized")
        self.movement_controls_group.setEnabled(False)
        self.disconnect_button.setEnabled(False)
        self.initialize_button.setEnabled(True)

        self.mock_hw_checkbox.setEnabled(True)
        self._on_mock_hw_changed(self.mock_hw_checkbox.checkState())

        self._update_position_display() # Resets position display to "-"

    def _on_mock_hw_changed(self, state):
        is_mock = bool(state == Qt.Checked) # state is an int from Qt.CheckState
        print(f"UI: Mock HW checkbox changed. is_mock: {is_mock}, initialize_button enabled: {self.initialize_button.isEnabled()}")
        # Only enable/disable config inputs if the stage is not currently initialized
        # (i.e., the initialize_button is the one that's currently active for user input)
        if self.initialize_button.isEnabled():
            self.mm_config_file_input.setEnabled(not is_mock)
            self.stage_device_label_input.setEnabled(True) # Always enabled when in config mode

            # Optionally, reset mm_config_file_input if switching to !is_mock and it's empty
            if not is_mock and not self.mm_config_file_input.text():
                 self.mm_config_file_input.setText("path/to/your/MMConfig.cfg") # Default placeholder
            # If switching to mock, and config was placeholder, could clear or leave as is.
            # For now, leave as is, as it's disabled anyway.


    def _get_step_size(self) -> float:
        if not self.stage: return 0.0
        try:
            val = float(self.step_size_input.text())
            return val if val > 0 else 0.0
        except ValueError:
            print("Error: Invalid step size input.")
            return 0.0

    def _get_jog_speed(self) -> float:
        if not self.stage: return 0.0
        try:
            val = float(self.jog_speed_input.text())
            return val if val > 0 else 0.0
        except ValueError:
            print("Error: Invalid jog speed input.")
            return 0.0

    def _update_position_display(self):
        if self.stage:
            current_pos = self.stage.get_position()
            self.current_position_display.setText(f"{current_pos:.2f}")
        else:
            self.current_position_display.setText("-")

    def _on_step_forward(self):
        if not self.stage: return
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop()
            print(f"UI: Step Forward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "forward")
            self._update_position_display()

    def _on_step_backward(self):
        if not self.stage: return
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop()
            print(f"UI: Step Backward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "backward")
            self._update_position_display()

    def _on_jog_forward(self):
        if not self.stage: return
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop()
            print(f"UI: Jog Forward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "forward")
            self._update_position_display()

    def _on_jog_backward(self):
        if not self.stage: return
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop()
            print(f"UI: Jog Backward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "backward")
            self._update_position_display()

    def _on_stop_jog(self):
        if not self.stage: return
        print("UI: Stop Jog clicked.")
        self.stage.stop()
        self._update_position_display()

if __name__ == "__main__":
    import napari
    import sys
    import os
    # QApplication needs to be imported and an instance created for widgets to work
    from qtpy.QtWidgets import QApplication

    # Ensure QApplication instance exists. Important for standalone execution.
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    try:
        # Try relative import for package structure
        from ..hardware.stage import Stage
    except ImportError:
        # Fallback for direct script execution
        module_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
        # Now that module_path (project root) is in sys.path, this should work:
        from microscope_control.hardware.stage import Stage


    viewer = napari.Viewer()
    widget = StageControlWidget(viewer)
    viewer.window.add_dock_widget(widget, area="right", name="Stage Control")
    napari.run()
