import unittest
from unittest.mock import patch, MagicMock
import sys
import os

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, project_root)

from pymmcore_plus import CMMCorePlus, DeviceType
from src.microscope_control.hardware.stage import Stage


class TestStageWithRealHardwareAccess(unittest.TestCase):
    """Tests for Stage when mock_hw=False, interacting with a mocked CMMCorePlus."""

    def setUp(self):
        self.class_patcher = patch('src.microscope_control.hardware.stage.CMMCorePlus', spec=CMMCorePlus)
        self.MockCMMCorePlusClass = self.class_patcher.start()

        # Changed: Removed spec=CMMCorePlus for more flexibility with inherited methods
        self.mock_core_instance = MagicMock()
        self.MockCMMCorePlusClass.instance.return_value = self.mock_core_instance

        self.INITIAL_X_POS = 0.0
        self.mock_core_instance.getLoadedDevices.return_value = []
        self.mock_core_instance.getDeviceType.return_value = DeviceType.XYStage
        self.mock_core_instance.getXPosition.return_value = self.INITIAL_X_POS

        self.config_file = "dummy.cfg"
        self.stage_label = "TestASIStageHW"
        self.adapter_name = "TestASIAdapter"
        self.device_name_in_adapter = "TestASIDevice"

        self.stage = Stage(
            mm_config_file=self.config_file,
            stage_device_label=self.stage_label,
            adapter_name=self.adapter_name,
            device_name=self.device_name_in_adapter,
            mock_hw=False
        )

    def tearDown(self):
        self.class_patcher.stop()

    def test_initialization_success(self):
        self.MockCMMCorePlusClass.instance.assert_called_once()
        self.assertIs(self.stage.core, self.mock_core_instance)
        self.mock_core_instance.loadDevice.assert_called_once_with(
            self.stage_label, self.adapter_name, self.device_name_in_adapter
        )
        self.mock_core_instance.initializeDevice.assert_called_once_with(self.stage_label)
        self.mock_core_instance.getXPosition.assert_called_with(self.stage_label)
        self.assertEqual(self.stage.get_position(), self.INITIAL_X_POS)
        self.assertFalse(self.stage.mock_hw)

    def test_initialization_device_already_loaded(self):
        self.class_patcher.stop()
        local_class_patcher = patch('src.microscope_control.hardware.stage.CMMCorePlus', spec=CMMCorePlus)
        MockCMMCorePlusClass_local = local_class_patcher.start()
        # Changed: Removed spec=CMMCorePlus
        mock_core_local = MagicMock()
        MockCMMCorePlusClass_local.instance.return_value = mock_core_local

        mock_core_local.getLoadedDevices.return_value = [self.stage_label]
        mock_core_local.getDeviceType.return_value = DeviceType.XYStage
        mock_core_local.getXPosition.return_value = 5.0

        stage = Stage(
            mm_config_file=self.config_file, stage_device_label=self.stage_label,
            adapter_name=self.adapter_name, device_name=self.device_name_in_adapter, mock_hw=False
        )
        MockCMMCorePlusClass_local.instance.assert_called_once()
        mock_core_local.loadDevice.assert_not_called()
        mock_core_local.initializeDevice.assert_not_called()
        self.assertTrue(mock_core_local.getXPosition.called)
        self.assertFalse(stage.mock_hw)
        self.assertEqual(stage.get_position(), 5.0)
        local_class_patcher.stop()
        self.class_patcher.start()

    def test_initialization_load_device_fails_runtime_error(self):
        self.class_patcher.stop()
        local_class_patcher = patch('src.microscope_control.hardware.stage.CMMCorePlus', spec=CMMCorePlus)
        MockCMMCorePlusClass_local = local_class_patcher.start()
        # Changed: Removed spec=CMMCorePlus
        mock_core_local = MagicMock()
        MockCMMCorePlusClass_local.instance.return_value = mock_core_local

        mock_core_local.getLoadedDevices.return_value = []
        mock_core_local.loadDevice.side_effect = RuntimeError("Failed to load device")

        stage = Stage(
            mm_config_file=self.config_file, stage_device_label="FailStageLoad",
            adapter_name=self.adapter_name, device_name=self.device_name_in_adapter, mock_hw=False
        )
        self.assertTrue(stage.mock_hw)
        self.assertIsInstance(stage.core, MagicMock)
        self.assertIsNot(stage.core, mock_core_local)
        local_class_patcher.stop()
        self.class_patcher.start()

    def test_initialization_init_device_fails_runtime_error(self):
        self.class_patcher.stop()
        local_class_patcher = patch('src.microscope_control.hardware.stage.CMMCorePlus', spec=CMMCorePlus)
        MockCMMCorePlusClass_local = local_class_patcher.start()
        # Changed: Removed spec=CMMCorePlus
        mock_core_local = MagicMock()
        MockCMMCorePlusClass_local.instance.return_value = mock_core_local

        mock_core_local.getLoadedDevices.return_value = []
        mock_core_local.getDeviceType.return_value = DeviceType.XYStage
        mock_core_local.loadDevice.return_value = None
        mock_core_local.initializeDevice.side_effect = RuntimeError("Failed to initialize")

        stage = Stage(
            mm_config_file=self.config_file, stage_device_label="FailInitStage",
            adapter_name=self.adapter_name, device_name=self.device_name_in_adapter, mock_hw=False
        )
        self.assertTrue(stage.mock_hw)
        self.assertIsInstance(stage.core, MagicMock)
        self.assertIsNot(stage.core, mock_core_local)
        local_class_patcher.stop()
        self.class_patcher.start()

    def test_get_position_hw(self):
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.return_value = 50.75
        pos = self.stage.get_position()
        self.mock_core_instance.getXPosition.assert_called_once_with(self.stage_label)
        self.assertAlmostEqual(pos, 50.75)
        self.assertAlmostEqual(self.stage._current_position, 50.75)

    def test_get_position_hw_runtime_error(self):
        self.stage._current_position = 30.0
        self.mock_core_instance.getXPosition.side_effect = RuntimeError("getXPosition error")
        pos = self.stage.get_position()
        self.assertAlmostEqual(pos, 30.0)

    def test_move_step_forward_hw(self):
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.side_effect = [self.INITIAL_X_POS, self.INITIAL_X_POS + 5.0, self.INITIAL_X_POS + 5.0]
        self.stage.move_step(5.0, "forward")
        self.mock_core_instance.setXPosition.assert_called_once_with(self.stage_label, self.INITIAL_X_POS + 5.0)
        self.mock_core_instance.waitForDevice.assert_called_once_with(self.stage_label)
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 2)
        self.assertAlmostEqual(self.stage.get_position(), self.INITIAL_X_POS + 5.0)

    def test_move_step_backward_hw(self):
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.side_effect = [self.INITIAL_X_POS, self.INITIAL_X_POS - 3.0, self.INITIAL_X_POS - 3.0]
        self.stage.move_step(3.0, "backward")
        self.mock_core_instance.setXPosition.assert_called_once_with(self.stage_label, self.INITIAL_X_POS - 3.0)
        self.mock_core_instance.waitForDevice.assert_called_once_with(self.stage_label)
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 2)
        self.assertAlmostEqual(self.stage.get_position(), self.INITIAL_X_POS - 3.0)

    def test_move_step_hw_runtime_error_on_set(self):
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.side_effect = [self.INITIAL_X_POS, self.INITIAL_X_POS]
        self.mock_core_instance.setXPosition.side_effect = RuntimeError("setXPosition error")
        self.stage.move_step(5.0, "forward")
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 2)
        self.assertAlmostEqual(self.stage._current_position, self.INITIAL_X_POS)

    def test_jog_forward_hw(self):
        self.mock_core_instance.getXPosition.reset_mock()
        jog_speed = 10.0
        expected_relative_move = jog_speed * 0.05
        self.mock_core_instance.getXPosition.side_effect = [self.INITIAL_X_POS + expected_relative_move, self.INITIAL_X_POS + expected_relative_move]
        self.stage.jog(jog_speed, "forward")
        self.mock_core_instance.setRelativeXPosition.assert_called_once_with(self.stage_label, expected_relative_move)
        self.mock_core_instance.waitForDevice.assert_called_once_with(self.stage_label)
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 1)
        self.assertAlmostEqual(self.stage.get_position(), self.INITIAL_X_POS + expected_relative_move)

    def test_jog_hw_runtime_error_on_set_relative(self):
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.return_value = self.INITIAL_X_POS
        self.mock_core_instance.setRelativeXPosition.side_effect = RuntimeError("setRelativeXPosition error")
        self.stage.jog(10.0, "forward")
        self.assertFalse(self.stage._is_jogging)
        self.mock_core_instance.getXPosition.assert_called_once()
        self.assertAlmostEqual(self.stage._current_position, self.INITIAL_X_POS)

    def test_stop_hw(self):
        self.mock_core_instance.getXPosition.reset_mock()
        jog_step = 10.0 * 0.05
        pos_after_jog = self.INITIAL_X_POS + jog_step
        # side_effect: [update in jog, update in stop, get_position() in assert]
        self.mock_core_instance.getXPosition.side_effect = [pos_after_jog, pos_after_jog, pos_after_jog]
        self.stage.jog(10.0, "forward")

        self.stage._is_jogging = True
        self.stage.stop()
        self.mock_core_instance.stop.assert_called_once_with(self.stage_label)
        self.assertFalse(self.stage._is_jogging)
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 2)
        self.assertAlmostEqual(self.stage.get_position(), pos_after_jog)

    def test_stop_hw_runtime_error(self):
        self.stage._is_jogging = True
        self.mock_core_instance.getXPosition.reset_mock()
        self.mock_core_instance.getXPosition.return_value = self.INITIAL_X_POS
        self.mock_core_instance.stop.side_effect = RuntimeError("stop error")
        self.stage.stop()
        self.assertFalse(self.stage._is_jogging)
        self.mock_core_instance.getXPosition.assert_called_once()
        self.assertAlmostEqual(self.stage._current_position, self.INITIAL_X_POS)

    def test_move_step_while_conceptually_jogging(self):
        self.stage._is_jogging = True
        self.mock_core_instance.getXPosition.reset_mock()
        pos_after_stop = self.INITIAL_X_POS + 1.0
        pos_after_move = pos_after_stop + 5.0
        # side_effect: [update in stop, current_x in move, update in move, get_position() in assert]
        self.mock_core_instance.getXPosition.side_effect = [
            pos_after_stop, pos_after_stop, pos_after_move, pos_after_move
        ]
        self.stage.move_step(5.0, "forward")
        self.mock_core_instance.stop.assert_called_once_with(self.stage_label)
        self.assertFalse(self.stage._is_jogging)
        self.mock_core_instance.setXPosition.assert_called_with(self.stage_label, pos_after_move)
        self.assertEqual(self.mock_core_instance.getXPosition.call_count, 3)
        self.assertAlmostEqual(self.stage.get_position(), pos_after_move)


@patch('src.microscope_control.hardware.stage.CMMCorePlus', spec=CMMCorePlus)
class TestStageMockHWMode(unittest.TestCase):

    def test_mock_hw_mode_initialization(self, MockCMMCorePlusClass): # Mock injected by decorator
        stage = Stage(mock_hw=True, stage_device_label="TestMockStage")
        self.assertTrue(stage.mock_hw)
        self.assertIsInstance(stage.core, MagicMock)
        MockCMMCorePlusClass.instance.assert_not_called()
        self.assertEqual(stage.get_position(), 0.0)

    def test_mock_hw_mode_get_position(self, MockCMMCorePlusClass):
        stage = Stage(mock_hw=True, stage_device_label="MyMockStage")
        # When mock_hw=True, get_position returns self._current_position directly.
        # The stage.core.getXPosition is configured in Stage.__init__ but not used by get_position in mock mode.
        stage._current_position = 25.0

        self.assertEqual(stage.get_position(), 25.0)
        MockCMMCorePlusClass.instance.assert_not_called()
        # Verify that stage.core.getXPosition was NOT called by stage.get_position()
        stage.core.getXPosition.assert_not_called()


    def test_mock_hw_mode_move_step(self, MockCMMCorePlusClass):
        stage = Stage(mock_hw=True, stage_device_label="MockStage")
        stage._current_position = 10.0
        stage.move_step(5.0, "forward")
        self.assertEqual(stage.get_position(), 15.0)
        MockCMMCorePlusClass.instance.assert_not_called()
        stage.core.setXPosition.assert_not_called()

    def test_mock_hw_mode_jog(self, MockCMMCorePlusClass):
        stage = Stage(mock_hw=True, stage_device_label="AnotherMock")
        stage._current_position = 0.0
        stage.jog(10.0, "forward")
        self.assertAlmostEqual(stage.get_position(), 0.5)
        self.assertTrue(stage._is_jogging)
        MockCMMCorePlusClass.instance.assert_not_called()
        stage.core.setRelativeXPosition.assert_not_called()

    def test_mock_hw_mode_stop(self, MockCMMCorePlusClass):
        stage = Stage(mock_hw=True)
        stage._is_jogging = True
        stage.stop()
        self.assertFalse(stage._is_jogging)
        MockCMMCorePlusClass.instance.assert_not_called()
        stage.core.stop.assert_not_called()

if __name__ == '__main__':
    unittest.main()
