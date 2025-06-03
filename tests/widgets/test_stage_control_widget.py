import unittest
from unittest.mock import MagicMock, patch
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

mock_napari = MagicMock()
sys.modules['napari'] = mock_napari
sys.modules['napari.viewer'] = MagicMock()

from qtpy.QtWidgets import QApplication, QLineEdit, QCheckBox, QPushButton, QLabel, QWidget, QGroupBox
from qtpy.QtCore import Qt

try:
    from src.microscope_control.hardware.stage import Stage
except ImportError:
    Stage = MagicMock

from src.microscope_control.widgets.stage_control_widget import StageControlWidget

app = None
def setUpModule():
    global app
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

def tearDownModule():
    global app
    if app:
        app.quit()
    app = None


class TestStageControlWidgetInitialization(unittest.TestCase):

    def setUp(self):
        self.mock_viewer = MagicMock(name="MockViewer")

        self.stage_patcher = patch('src.microscope_control.widgets.stage_control_widget.Stage', spec=Stage)
        self.MockStageClass = self.stage_patcher.start()

        self.mock_stage_instance = MagicMock(spec=Stage)
        self.mock_stage_instance.mock_hw = False
        # Ensure stage_device_label attribute exists on the mock_stage_instance
        self.mock_stage_instance.stage_device_label = "DefaultTestLabel"
        self.MockStageClass.return_value = self.mock_stage_instance

        self.widget = StageControlWidget(self.mock_viewer)

        # Mock UI elements after widget initialization
        self.widget.mm_config_file_input = MagicMock(spec=QLineEdit)
        self.widget.stage_device_label_input = MagicMock(spec=QLineEdit)
        self.widget.mock_hw_checkbox = MagicMock(spec=QCheckBox)
        self.widget.initialize_button = MagicMock(spec=QPushButton)
        self.widget.disconnect_button = MagicMock(spec=QPushButton)
        self.widget.status_label = MagicMock(spec=QLabel)
        self.widget.movement_controls_group = MagicMock(spec=QGroupBox)
        self.widget.current_position_display = MagicMock(spec=QLabel)

        # Default return values for UI mocks
        self.widget.mm_config_file_input.text.return_value = "dummy.cfg"
        self.widget.stage_device_label_input.text.return_value = "TestStageLabel"
        self.widget.mock_hw_checkbox.isChecked.return_value = False
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked


    def tearDown(self):
        self.stage_patcher.stop()
        del self.widget

    def test_initial_ui_state(self):
        self.stage_patcher.stop()

        if QApplication.instance() is None:
            QApplication(sys.argv)

        widget_init_test = StageControlWidget(self.mock_viewer)

        self.assertIsNone(widget_init_test.stage)
        self.assertTrue(widget_init_test.initialize_button.isEnabled())
        self.assertFalse(widget_init_test.disconnect_button.isEnabled())
        self.assertFalse(widget_init_test.movement_controls_group.isEnabled())
        self.assertEqual(widget_init_test.status_label.text(), "Status: Not Initialized")
        self.assertTrue(widget_init_test.mock_hw_checkbox.isChecked())
        self.assertFalse(widget_init_test.mm_config_file_input.isEnabled())

        self.stage_patcher.start()


    def test_on_initialize_stage_success_real_hw(self):
        self.widget.mock_hw_checkbox.isChecked.return_value = False
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked
        self.widget.mm_config_file_input.text.return_value = "real.cfg"
        self.widget.stage_device_label_input.text.return_value = "RealStage"

        self.mock_stage_instance.mock_hw = False
        self.mock_stage_instance.stage_device_label = "RealStage"
        self.mock_stage_instance.get_position.return_value = 10.0

        self.widget._on_initialize_stage()

        self.MockStageClass.assert_called_once_with(
            mm_config_file="real.cfg", stage_device_label="RealStage", mock_hw=False
        )
        self.assertIs(self.widget.stage, self.mock_stage_instance)
        # Check for the specific success message part
        self.assertTrue("Status: Initialized (Real HW: RealStage)" in self.widget.status_label.setText.call_args[0][0])
        self.widget.movement_controls_group.setEnabled.assert_called_with(True)
        self.widget.disconnect_button.setEnabled.assert_called_with(True)
        self.widget.initialize_button.setEnabled.assert_called_with(False)
        self.widget.mm_config_file_input.setEnabled.assert_called_with(False)
        self.widget.stage_device_label_input.setEnabled.assert_called_with(False)
        self.widget.mock_hw_checkbox.setEnabled.assert_called_with(False)
        self.mock_stage_instance.get_position.assert_called_once()


    def test_on_initialize_stage_success_mock_hw(self):
        self.widget.mock_hw_checkbox.isChecked.return_value = True
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Checked
        self.widget.mm_config_file_input.text.return_value = "any.cfg"
        self.widget.stage_device_label_input.text.return_value = "MockStageLabel"

        self.mock_stage_instance.mock_hw = True
        self.mock_stage_instance.stage_device_label = "MockStageLabel"
        self.mock_stage_instance.get_position.return_value = 0.0

        self.widget._on_initialize_stage()

        self.MockStageClass.assert_called_once_with(
            mm_config_file="any.cfg", stage_device_label="MockStageLabel", mock_hw=True
        )
        self.assertIs(self.widget.stage, self.mock_stage_instance)
        self.assertTrue("Status: Initialized (Mock: MockStageLabel)" in self.widget.status_label.setText.call_args[0][0])
        self.widget.movement_controls_group.setEnabled.assert_called_with(True)
        self.widget.disconnect_button.setEnabled.assert_called_with(True)
        self.widget.initialize_button.setEnabled.assert_called_with(False)


    def test_on_initialize_stage_real_hw_fallback_to_mock(self):
        self.widget.mock_hw_checkbox.isChecked.return_value = False
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked
        self.widget.mm_config_file_input.text.return_value = "real.cfg"
        self.widget.stage_device_label_input.text.return_value = "RealStage"

        self.mock_stage_instance.mock_hw = True
        self.mock_stage_instance.stage_device_label = "RealStage"
        self.mock_stage_instance.get_position.return_value = 0.0

        self.widget._on_initialize_stage()

        self.MockStageClass.assert_called_once_with(
            mm_config_file="real.cfg", stage_device_label="RealStage", mock_hw=False
        )
        self.assertTrue(self.widget.stage.mock_hw)
        self.assertTrue("Status: Error - Real HW init failed. Using mock stage for 'RealStage'." in self.widget.status_label.setText.call_args[0][0])
        self.widget.mock_hw_checkbox.setChecked.assert_called_with(True)

    def test_on_initialize_stage_failure_runtime_error(self):
        self.widget.mock_hw_checkbox.isChecked.return_value = False
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked
        self.widget.mm_config_file_input.text.return_value = "bad.cfg" # Ensure it attempts real init
        self.widget.stage_device_label_input.text.return_value = "ErrorStage"

        self.MockStageClass.side_effect = RuntimeError("Test Stage Init Error")

        self.widget._on_initialize_stage()

        self.assertIsNone(self.widget.stage)
        self.widget.movement_controls_group.setEnabled.assert_called_with(False)
        # Check if the last call to setText contains the error message
        last_call_args = self.widget.status_label.setText.call_args_list[-1][0][0]
        self.assertTrue("Status: Error - Test Stage Init Error" in last_call_args)
        self.widget.initialize_button.setEnabled.assert_called_with(True)
        self.widget.mock_hw_checkbox.setEnabled.assert_called_with(True)
        self.widget.mm_config_file_input.setEnabled.assert_called_with(True)
        self.widget.stage_device_label_input.setEnabled.assert_called_with(True)


    def test_on_initialize_stage_validation_fail_real_hw(self):
        self.widget.mock_hw_checkbox.isChecked.return_value = False
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked
        self.widget.mm_config_file_input.text.return_value = "" # Empty config

        self.widget._on_initialize_stage()

        self.MockStageClass.assert_not_called()
        self.widget.status_label.setText.assert_called_with(
            "Status: Error - Config file and device label are required for real hardware."
        )
        self.assertIsNone(self.widget.stage)


    def test_on_disconnect_stage(self):
        # Simulate initialized state (real hardware)
        self.widget.stage = self.mock_stage_instance
        self.mock_stage_instance.stage_device_label = "PreviouslyRealStage" # Set for the print
        self.widget.initialize_button.setEnabled(False)
        self.widget.disconnect_button.setEnabled(True)
        self.widget.movement_controls_group.setEnabled(True)
        self.widget.mm_config_file_input.setEnabled(False)
        self.widget.stage_device_label_input.setEnabled(False)
        self.widget.mock_hw_checkbox.setEnabled(False)
        self.widget.mock_hw_checkbox.isChecked.return_value = False # Was real
        self.widget.mock_hw_checkbox.checkState.return_value = Qt.Unchecked


        self.widget._on_disconnect_stage()

        self.assertIsNone(self.widget.stage)
        self.widget.movement_controls_group.setEnabled.assert_called_with(False)
        self.widget.disconnect_button.setEnabled.assert_called_with(False)
        self.widget.initialize_button.setEnabled.assert_called_with(True)
        self.widget.mock_hw_checkbox.setEnabled.assert_called_with(True)

        # _on_mock_hw_changed is called by _on_disconnect_stage.
        # Since mock_hw_checkbox is now False (unchecked), mm_config_file_input should be enabled.
        self.widget.mm_config_file_input.setEnabled.assert_called_with(True)
        self.widget.stage_device_label_input.setEnabled.assert_called_with(True) # Always true in _on_mock_hw_changed current form

        self.widget.status_label.setText.assert_called_with("Status: Not Initialized")
        self.widget.current_position_display.setText.assert_called_with("-")


    def test_on_mock_hw_changed(self):
        # Scenario 1: Stage not initialized (initialize_button is enabled)
        self.widget.initialize_button.isEnabled.return_value = True

        self.widget._on_mock_hw_changed(Qt.Checked) # Mock True
        self.widget.mm_config_file_input.setEnabled.assert_called_with(False)

        self.widget._on_mock_hw_changed(Qt.Unchecked) # Mock False
        self.widget.mm_config_file_input.setEnabled.assert_called_with(True)

        # Scenario 2: Stage initialized (initialize_button is disabled)
        self.widget.initialize_button.isEnabled.return_value = False
        self.widget.mm_config_file_input.reset_mock()

        self.widget._on_mock_hw_changed(Qt.Checked)
        self.widget.mm_config_file_input.setEnabled.assert_not_called()

        self.widget._on_mock_hw_changed(Qt.Unchecked)
        self.widget.mm_config_file_input.setEnabled.assert_not_called()

if __name__ == '__main__':
    unittest.main()
