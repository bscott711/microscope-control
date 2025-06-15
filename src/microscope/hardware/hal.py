from typing import Optional

import serial
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda.handlers import OMEZarrWriter
from useq import MDASequence

# Import all the dedicated hardware controllers
from .camera import CameraHardwareController
from .crisp import CRISPHardwareController
from .galvo import GalvoHardwareController
from .plogic import PLogicHardwareController
from .stage import StageHardwareController


class HardwareAbstractionLayer:
    """
    A Facade that provides a simplified, high-level interface to the
    complex microscope hardware subsystem. This is the primary entry point
    into the Model for the Controller (`engine.py`).
    """

    def __init__(self, mmc: CMMCorePlus):
        self.mmc = mmc

        # The HAL instantiates and owns all hardware controllers
        self._camera_ctrl = CameraHardwareController()
        self._stage_ctrl = StageHardwareController()
        self._galvo_ctrl = GalvoHardwareController()
        self._plogic_ctrl = PLogicHardwareController()
        self._crisp_ctrl = CRISPHardwareController()

        # This would be loaded from a user-editable config file
        self._com_port = "COM4"
        self._crisp_addr = "32"  # From your cfg: CRISPAFocus:Z:32

        # To store the MDA writer for proper cleanup
        self._mda_writer: Optional[OMEZarrWriter] = None

    def _execute_serial_action(self, action, *args, **kwargs):
        """Context manager for safe serial communication."""
        try:
            with serial.Serial(self._com_port, 115200, timeout=1) as ser:
                return action(ser, *args, **kwargs)
        except serial.SerialException as e:
            raise ConnectionError(f"HAL: Failed to connect to Tiger on {self._com_port}: {e}")

    def setup_and_run_z_stack(self, params: dict):
        """
        The primary high-level method for the experiment. It coordinates all
        hardware setup and then starts the MDA.
        """
        print("HAL: Coordinating hardware setup and running Z-stack...")

        # 1. Configure hardware
        self._camera_ctrl.set_trigger_mode(self.mmc, "Level Trigger Mode")

        def setup_asi_hardware(ser):
            self._galvo_ctrl.configure_for_z_stack(ser, params)
            self._plogic_ctrl.configure_for_triggers(ser, params)

        self._execute_serial_action(setup_asi_hardware)

        # 2. Define the acquisition sequence
        sequence = MDASequence(time_plan=params["num_slices"])  # type: ignore

        # 3. Setup the data writer, store it for cleanup, and connect events
        self._mda_writer = OMEZarrWriter(params["save_path"], overwrite=True)
        self.mmc.mda.events.sequenceStarted.connect(self._mda_writer.sequenceStarted)
        self.mmc.mda.events.frameReady.connect(self._mda_writer.frameReady)
        self.mmc.mda.events.sequenceFinished.connect(self._mda_writer.sequenceFinished)

        print("HAL: Starting MDA engine. System is armed and waiting for triggers.")
        self.mmc.mda.run(sequence)

    def final_cleanup(self):
        """
        Called at the end of an acquisition to ensure a safe state and
        disconnect event handlers to prevent memory leaks.
        """
        print("HAL: Performing final cleanup.")
        if self._mda_writer:
            self.mmc.mda.events.sequenceStarted.disconnect(self._mda_writer.sequenceStarted)
            self.mmc.mda.events.frameReady.disconnect(self._mda_writer.frameReady)
            self.mmc.mda.events.sequenceFinished.disconnect(self._mda_writer.sequenceFinished)
            self._mda_writer = None
            print("HAL: MDA writer disconnected.")

    # --- Stage Control API ---

    def move_stage_relative(self, axis: str, distance_um: float):
        """Moves a stage axis by a relative amount in micrometers."""
        self._execute_serial_action(self._stage_ctrl.move_relative, axis, distance_um)

    def get_stage_position_um(self, axes: list[str]) -> dict[str, float]:
        """Gets the current position of one or more axes in micrometers."""
        return self._execute_serial_action(self._stage_ctrl.get_position_um, axes)

    def wait_for_stage(self):
        """Waits for all stage motion to complete."""
        self._execute_serial_action(self._stage_ctrl.wait_for_device)

    # --- CRISP Control API ---

    def crisp_lock(self):
        """Engages the CRISP lock."""
        self._execute_serial_action(self._crisp_ctrl.lock, self._crisp_addr)

    def crisp_unlock(self):
        """Disengages the CRISP lock."""
        self._execute_serial_action(self._crisp_ctrl.unlock, self._crisp_addr)

    def crisp_save_calibration(self):
        """Saves the current CRISP calibration to the card."""
        self._execute_serial_action(self._crisp_ctrl.save_calibration, self._crisp_addr)

    # --- Camera Control API ---

    def set_camera_exposure(self, exposure_ms: float):
        """Sets the exposure time for the active camera(s)."""
        self._camera_ctrl.set_exposure(self.mmc, exposure_ms)

    def get_camera_exposure(self) -> float:
        """Gets the current exposure time from the core."""
        return self._camera_ctrl.get_exposure(self.mmc)
