from magicgui.widgets import (
    Container,
    LineEdit,
    CheckBox,
    Button,
    Label,
    FloatSpinBox,
)
from qtpy.QtWidgets import QApplication  # For processEvents, if needed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import napari

from ..hardware.stage import (
    Stage,
)  # Assuming this path is correct for napari plugin structure

# Default values from the original Qt widget
DEFAULT_MM_CONFIG_FILE_TEXT = "hardware_profiles/20250523-OPM.cfg"
DEFAULT_STAGE_LABEL_TEXT = "ASI XYStage"
DEFAULT_STEP_SIZE_TEXT = "1.0"
DEFAULT_JOG_SPEED_TEXT = "10.0"


class StageControlWidget(Container):
    def __init__(self, viewer: "napari.Viewer"):
        super().__init__()
        self.viewer = viewer
        self.stage = None  # Stage instance will be created on initialization

        # --- Configuration UI ---
        self.mm_config_file_input = LineEdit(
            value=DEFAULT_MM_CONFIG_FILE_TEXT, label="MM Config File:"
        )
        self.stage_device_label_input = LineEdit(
            value=DEFAULT_STAGE_LABEL_TEXT, label="Stage Device Label:"
        )
        self.mock_hw_checkbox = CheckBox(text="Use Mock Hardware", value=True)

        self.initialize_button = Button(text="Initialize Stage")
        self.disconnect_button = Button(text="Disconnect Stage", enabled=False)

        self.status_label = Label(value="Status: Not Initialized")
        # self.status_label.native.setWordWrap(True) # If word wrap is needed

        config_group_widgets = [
            self.mm_config_file_input,
            self.stage_device_label_input,
            self.mock_hw_checkbox,
            Container(
                widgets=[self.initialize_button, self.disconnect_button],
                layout="horizontal",
                labels=False,
            ),
            self.status_label,
        ]
        # Using a Label as a title for the group
        config_title = Label(value="Configuration")
        # config_title.native.setStyleSheet("font-weight: bold;") # Example for styling

        # --- Movement Controls UI ---
        self.step_size_input = FloatSpinBox(  # Changed from RangeEdit
            value=float(DEFAULT_STEP_SIZE_TEXT),
            label="Step Size (um):",
            min=0.01,
            max=10000.0,
            step=0.1,  # FloatSpinBox often benefits from an explicit step
        )
        self.step_forward_button = Button(text="Step Forward")
        self.step_backward_button = Button(text="Step Backward")

        self.jog_speed_input = FloatSpinBox(  # Changed from RangeEdit
            value=float(DEFAULT_JOG_SPEED_TEXT),
            label="Jog Speed (um/s):",
            min=0.1,
            max=1000.0,
            step=0.1,  # FloatSpinBox often benefits from an explicit step
        )
        self.jog_forward_button = Button(text="Jog Forward")
        self.jog_backward_button = Button(text="Jog Backward")

        self.stop_jog_button = Button(text="Stop Jog")

        self.current_position_display = Label(value="-")
        current_pos_container = Container(
            widgets=[
                Label(value="Current Position (um):"),
                self.current_position_display,
            ],
            layout="horizontal",
            labels=False,
        )

        self.movement_controls_group = Container(
            widgets=[
                self.step_size_input,
                Container(
                    widgets=[self.step_backward_button, self.step_forward_button],
                    layout="horizontal",
                    labels=False,
                ),
                self.jog_speed_input,
                Container(
                    widgets=[self.jog_backward_button, self.jog_forward_button],
                    layout="horizontal",
                    labels=False,
                ),
                self.stop_jog_button,
                current_pos_container,
            ],
            enabled=False,
            labels=False,  # Individual widgets have labels
        )
        movement_title = Label(value="Movement Controls")
        # movement_title.native.setStyleSheet("font-weight: bold;")

        # Add all parts to the main widget (self)
        self.extend(
            [
                config_title,
                *config_group_widgets,  # Unpack the list of widgets
                movement_title,
                self.movement_controls_group,
            ]
        )

        # Connect signals to slots
        self.initialize_button.clicked.connect(self._on_initialize_stage)
        self.disconnect_button.clicked.connect(self._on_disconnect_stage)
        # For magicgui.CheckBox, the signal is 'changed' and it passes the new boolean value
        self.mock_hw_checkbox.changed.connect(self._on_mock_hw_changed)

        self.step_forward_button.clicked.connect(self._on_step_forward)
        self.step_backward_button.clicked.connect(self._on_step_backward)
        self.jog_forward_button.clicked.connect(self._on_jog_forward)
        self.jog_backward_button.clicked.connect(self._on_jog_backward)
        self.stop_jog_button.clicked.connect(self._on_stop_jog)

        self._on_mock_hw_changed(self.mock_hw_checkbox.value)

    def _on_initialize_stage(self):
        if self.stage:  # If already initialized, disconnect first to ensure clean state
            self._on_disconnect_stage()

        mm_config = self.mm_config_file_input.value
        device_label = self.stage_device_label_input.value
        use_mock = self.mock_hw_checkbox.value

        if not use_mock and (not mm_config or not device_label):
            self.status_label.value = "Status: Error - Config file and device label are required for real hardware."
            return

        try:
            self.status_label.value = (
                f"Status: Initializing {'mock' if use_mock else device_label}..."
            )
            QApplication.processEvents()  # Allow UI to update status message

            self.stage = Stage(
                mm_config_file=mm_config,
                stage_device_label=device_label,
                mock_hw=use_mock,
            )

            # If Stage initialization failed and it fell back to mock_hw=True internally
            if self.stage.mock_hw and not use_mock:
                self.status_label.value = f"Status: Error - Real HW init failed. Using mock stage for '{device_label}'."
                self.mock_hw_checkbox.value = True  # Reflect fallback in UI
            else:  # Success or intended mock initialization
                status_msg = "Status: Initialized "
                if self.stage.mock_hw:
                    status_msg += f"(Mock: {device_label})"
                else:
                    status_msg += f"(Real HW: {device_label})"
                self.status_label.value = status_msg

            self.movement_controls_group.enabled = True
            self.disconnect_button.enabled = True
            self.initialize_button.enabled = False
            self.mm_config_file_input.enabled = False
            self.stage_device_label_input.enabled = False
            self.mock_hw_checkbox.enabled = False
            self._update_position_display()

        except (
            RuntimeError
        ) as e:  # Catch errors from Stage init (e.g., pymmcore issues)
            self.stage = None  # Ensure stage is None on failure
            self.status_label.value = f"Status: Error - {e}"
            self.movement_controls_group.enabled = False
            self.disconnect_button.enabled = False
            self.initialize_button.enabled = True
            # Re-enable config inputs based on mock_hw checkbox state
            self.mock_hw_checkbox.enabled = True
            self._on_mock_hw_changed(self.mock_hw_checkbox.value)
            self._update_position_display()  # Reset position text to "-"
        except Exception as e:  # Catch any other unexpected error
            self.stage = None
            self.status_label.value = f"Status: Unexpected error - {e}"
            self.movement_controls_group.enabled = False
            self.disconnect_button.enabled = False
            self.initialize_button.enabled = True
            self.mock_hw_checkbox.enabled = True
            self._on_mock_hw_changed(self.mock_hw_checkbox.value)
            self._update_position_display()

    def _on_disconnect_stage(self):
        if self.stage:
            print(
                f"Disconnecting stage: {self.stage.stage_device_label if self.stage.stage_device_label else 'N/A'}"
            )

        self.stage = None
        self.status_label.value = "Status: Not Initialized"
        self.movement_controls_group.enabled = False
        self.disconnect_button.enabled = False
        self.initialize_button.enabled = True

        self.mock_hw_checkbox.enabled = True
        self._on_mock_hw_changed(self.mock_hw_checkbox.value)

        self._update_position_display()  # Resets position display to "-"

    def _on_mock_hw_changed(self, is_mock: bool):
        print(
            f"UI: Mock HW checkbox changed. is_mock: {is_mock}, initialize_button enabled: {self.initialize_button.enabled}"
        )
        # Only enable/disable config inputs if the stage is not currently initialized
        # (i.e., the initialize_button is the one that's currently active for user input)
        if self.initialize_button.enabled:
            self.mm_config_file_input.enabled = not is_mock
            self.stage_device_label_input.enabled = (
                True  # Always enabled when in config mode
            )

            # Optionally, reset mm_config_file_input if switching to !is_mock and it's empty
            if not is_mock and not self.mm_config_file_input.value:
                self.mm_config_file_input.value = DEFAULT_MM_CONFIG_FILE_TEXT

    def _get_step_size(self) -> float:
        if not self.stage:
            return 0.0
        try:
            val = self.step_size_input.value
            return val if val > 0 else 0.0
        except ValueError:
            print(f"Error: Invalid step size input: {self.step_size_input.value}")
            return 0.0

    def _get_jog_speed(self) -> float:
        if not self.stage:
            return 0.0
        try:
            val = self.jog_speed_input.value
            return val if val > 0 else 0.0
        except ValueError:
            print(f"Error: Invalid jog speed input: {self.jog_speed_input.value}")
            return 0.0

    def _update_position_display(self):
        if self.stage:
            current_pos = self.stage.get_position()
            self.current_position_display.value = f"{current_pos:.2f}"
        else:
            self.current_position_display.value = "-"

    def _on_step_forward(self):
        if not self.stage:
            return
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop()
            print(f"UI: Step Forward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "forward")
            self._update_position_display()

    def _on_step_backward(self):
        if not self.stage:
            return
        step_size = self._get_step_size()
        if step_size > 0:
            self.stage.stop()
            print(f"UI: Step Backward clicked. Step size: {step_size}")
            self.stage.move_step(step_size, "backward")
            self._update_position_display()

    def _on_jog_forward(self):
        if not self.stage:
            return
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop()
            print(f"UI: Jog Forward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "forward")
            self._update_position_display()

    def _on_jog_backward(self):
        if not self.stage:
            return
        jog_speed = self._get_jog_speed()
        if jog_speed > 0:
            self.stage.stop()
            print(f"UI: Jog Backward clicked. Jog speed: {jog_speed}")
            self.stage.jog(jog_speed, "backward")
            self._update_position_display()

    def _on_stop_jog(self):
        if not self.stage:
            return
        print("UI: Stop Jog clicked.")
        self.stage.stop()
        self._update_position_display()


if __name__ == "__main__":
    import napari
    import sys
    import os
    # magicgui handles QApplication creation if shown standalone.
    # napari handles it when added as a dock widget.

    try:
        from ..hardware.stage import Stage
    except ImportError:
        # Fallback for direct script execution
        module_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        if module_path not in sys.path:
            sys.path.insert(0, module_path)
        from microscope_control.hardware.stage import Stage

    viewer = napari.Viewer()
    widget = StageControlWidget(viewer)

    # Add the magicgui widget to napari.
    # magicgui containers can often be added directly.
    viewer.window.add_dock_widget(widget, area="right", name="Stage Control (magicgui)")
    napari.run()
