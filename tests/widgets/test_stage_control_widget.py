import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the src directory to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

# Mock napari before it's imported by the widget
# This is to avoid issues in headless environments or if napari is not fully installed
# We are testing widget logic, not napari integration here.
mock_napari = MagicMock()
sys.modules['napari'] = mock_napari
sys.modules['napari.viewer'] = MagicMock()


from qtpy.QtWidgets import QApplication # Required for QLineEdit, etc.
# QApplication needs to be instantiated once for Qt widgets to be created, even if not shown
# This can be done globally or per test class/method.
# Using a global instance is often fine for test suites.
# If it causes issues between tests, it can be managed in setUp/tearDown.
app = None
def setUpModule():
    global app
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

def tearDownModule():
    global app
    app.quit()
    app = None


from src.microscope_control.widgets.stage_control_widget import StageControlWidget
from src.microscope_control.hardware.stage import Stage # Used for spec in MagicMock


class TestStageControlWidget(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Ensure QApplication instance exists for the test class
        # This might be redundant if setUpModule is effectively used by the test runner
        # but ensures safety if tests are run individually or by different runners.
        global app
        if QApplication.instance() is None:
           app = QApplication(sys.argv)


    def setUp(self):
        """Set up for each test."""
        # Mock the napari viewer instance
        self.mock_viewer = MagicMock(name="MockViewer")

        # Instantiate the widget with the mocked viewer
        self.widget = StageControlWidget(self.mock_viewer)

        # Replace the real Stage instance with a MagicMock
        # The Stage instance is created within StageControlWidget's __init__
        # So, we mock it after the widget is initialized.
        self.widget.stage = MagicMock(spec=Stage)

        # Set a default return value for get_position to avoid issues if it's called unexpectedly
        self.widget.stage.get_position.return_value = 0.0
        # Call update_position_display once to ensure the label is initialized based on mock
        self.widget._update_position_display()


    def test_widget_initialization(self):
        self.assertIsNotNone(self.widget)
        self.assertEqual(self.widget.step_size_input.text(), "1.0")
        self.assertEqual(self.widget.jog_speed_input.text(), "10.0")
        self.assertEqual(self.widget.current_position_display.text(), "0.00") # From _update_position_display in setUp

    def test_update_position_display(self):
        self.widget.stage.get_position.return_value = 123.456
        self.widget._update_position_display()
        self.assertEqual(self.widget.current_position_display.text(), "123.46") # Check formatting to 2 decimal places

        self.widget.stage.get_position.return_value = -78.9
        self.widget._update_position_display()
        self.assertEqual(self.widget.current_position_display.text(), "-78.90")

    def test_on_step_forward(self):
        self.widget.step_size_input.setText("5.5")
        self.widget.stage.get_position.return_value = 5.5 # Simulate position update

        self.widget._on_step_forward()

        self.widget.stage.stop.assert_called_once()
        self.widget.stage.move_step.assert_called_once_with(5.5, "forward")
        self.widget.stage.get_position.assert_called() # Called by _update_position_display
        self.assertEqual(self.widget.current_position_display.text(), "5.50")

    def test_on_step_backward(self):
        self.widget.step_size_input.setText("3.25")
        self.widget.stage.get_position.return_value = -3.25 # Simulate position update

        self.widget._on_step_backward()

        self.widget.stage.stop.assert_called_once()
        self.widget.stage.move_step.assert_called_once_with(3.25, "backward")
        self.widget.stage.get_position.assert_called()
        self.assertEqual(self.widget.current_position_display.text(), "-3.25")

    def test_on_step_invalid_input(self):
        self.widget.step_size_input.setText("abc") # Invalid input
        # _get_step_size now prints an error and returns 0.0
        # The stage.move_step should not be called if step_size <= 0

        self.widget._on_step_forward()

        self.widget.stage.stop.assert_not_called() # Because step_size will be 0.0, so no action
        self.widget.stage.move_step.assert_not_called()
        # get_position is still called by _update_position_display in widget init, but not again here
        # Let's reset mock and check again to be sure
        self.widget.stage.get_position.reset_mock()
        self.widget._on_step_forward() # Call again with invalid input
        self.widget.stage.get_position.assert_not_called()


    def test_on_jog_forward(self):
        self.widget.jog_speed_input.setText("15.0")
        # Position display updates to current position when jog starts
        self.widget.stage.get_position.return_value = 0.0

        self.widget._on_jog_forward()

        self.widget.stage.stop.assert_called_once() # Stops previous jog
        self.widget.stage.jog.assert_called_once_with(15.0, "forward")
        self.widget.stage.get_position.assert_called()
        self.assertEqual(self.widget.current_position_display.text(), "0.00")

    def test_on_jog_backward(self):
        self.widget.jog_speed_input.setText("7.7")
        self.widget.stage.get_position.return_value = 0.0

        self.widget._on_jog_backward()

        self.widget.stage.stop.assert_called_once()
        self.widget.stage.jog.assert_called_once_with(7.7, "backward")
        self.widget.stage.get_position.assert_called()
        self.assertEqual(self.widget.current_position_display.text(), "0.00")

    def test_on_jog_invalid_input(self):
        self.widget.jog_speed_input.setText("xyz")
        # _get_jog_speed now prints an error and returns 0.0
        # stage.jog should not be called if speed <= 0

        self.widget._on_jog_forward()

        self.widget.stage.stop.assert_not_called() # Because jog_speed will be 0.0
        self.widget.stage.jog.assert_not_called()
        self.widget.stage.get_position.reset_mock()
        self.widget._on_jog_forward() # Call again
        self.widget.stage.get_position.assert_not_called()


    def test_on_stop_jog(self):
        self.widget.stage.get_position.return_value = 10.5 # Position after stopping

        self.widget._on_stop_jog()

        self.widget.stage.stop.assert_called_once()
        self.widget.stage.get_position.assert_called()
        self.assertEqual(self.widget.current_position_display.text(), "10.50")

    @classmethod
    def tearDownClass(cls):
        # QApplication.quit() # Not strictly necessary if using setUpModule/tearDownModule
        # but good for completeness if managing app per class.
        # Let global tearDownModule handle it.
        pass

if __name__ == '__main__':
    unittest.main()
