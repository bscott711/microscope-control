# src/microscope/core/engine.py

import logging
import time
from itertools import groupby

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, QThread, Signal  # type: ignore
from useq import (
    MDAEvent,
    MDASequence,
    MultiPhaseTimePlan,
    TIntervalLoops,
    ZAboveBelow,
    ZRangeAround,
)

from .constants import HardwareConstants
from .hardware import (
    configure_galvo_for_hardware_timed_scan,
    configure_plogic_for_dual_nrt_pulses,
    disable_live_laser,
    reset_camera_trigger_mode_internal,
    send_tiger_command,
    set_camera_trigger_mode_level_high,
    set_piezo_sleep,
)
from .settings import AcquisitionSettings

logger = logging.getLogger(__name__)


class AcquisitionWorker(QObject):
    """
    Worker object for running hardware-timed acquisitions in a separate thread.
    """

    frameReady = Signal(object, object, object)
    acquisitionFinished = Signal(object)

    def __init__(self, mmc: CMMCorePlus, sequence: MDASequence, parent=None):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.hw = HardwareConstants()
        self._running = True
        self.settings: AcquisitionSettings | None = None

    def stop(self):
        """Stop the acquisition."""
        self._running = False

    def run(self):
        """Execute a hardware-timed MDA sequence."""
        original_autoshutter = self._mmc.getAutoShutter()
        original_timeout = self._mmc.getTimeoutMs()  # CORRECTED METHOD

        try:
            # Disable piezo sleep for the duration of the MDA
            set_piezo_sleep(self._mmc, self.hw, enabled=False)
            # Perform a single, one-time hardware setup
            self._setup_mda()
            # Execute the main loop for T and P axes
            self._execute_mda_loop()
        except Exception:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            # Re-enable piezo sleep after the MDA is complete
            set_piezo_sleep(self._mmc, self.hw, enabled=True)
            if self._mmc.isSequenceRunning():
                self._mmc.stopSequenceAcquisition()
            self._mmc.setAutoShutter(original_autoshutter)
            self._mmc.setTimeoutMs(original_timeout)
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Custom hardware-timed Z-stack completed.")

    def _setup_mda(self):
        """
        Perform one-time hardware configuration for the entire MDA sequence.
        """
        logger.info("Performing one-time MDA configuration...")
        self._mmc.setAutoShutter(False)

        if not self.sequence.z_plan:
            raise ValueError("Hardware-timed scan requires a Z-plan.")

        # Set camera trigger mode to Level High for the hardware-timed scan
        set_camera_trigger_mode_level_high(self._mmc, self.hw)

        num_z_slices = len(list(self.sequence.z_plan))
        step_size = self._get_z_step_size(self.sequence.z_plan)
        self.settings = AcquisitionSettings(
            num_slices=num_z_slices,
            step_size_um=step_size,
            camera_exposure_ms=self._mmc.getExposure(),
        )

        # Configure PLogic for the entire autonomous scan, this is not position-dependent
        configure_plogic_for_dual_nrt_pulses(self._mmc, self.settings, self.hw)

        # Manually enable the master laser control cell (8) for the MDA.
        # This avoids calling enable_live_laser() which would load a conflicting preset.
        logger.info("Enabling laser for MDA sequence.")
        plogic_addr_prefix = self.hw.plogic_label.split(":")[-1]
        send_tiger_command(self._mmc, "M E=8")
        send_tiger_command(self._mmc, f"{plogic_addr_prefix}CCA Y=0")  # Cell Type: Constant
        send_tiger_command(self._mmc, f"{plogic_addr_prefix}CCA Z=1")  # Value: HIGH

        logger.info("One-time MDA configuration complete.")

    def _execute_mda_loop(self):
        """
        Run the main T and P acquisition loop.
        """
        full_event_list = list(self.sequence)
        interval_s = self._get_time_interval_s(self.sequence.time_plan)
        last_time_point_start = 0.0

        def event_key(e):
            return e.index.get("t", 0), e.index.get("p", 0)

        for (t_idx, p_idx), group in groupby(full_event_list, key=event_key):
            if not self._running:
                break

            if interval_s > 0 and t_idx > 0:
                wait_time = (last_time_point_start + interval_s) - time.time()
                if wait_time > 0:
                    logger.info(f"Waiting for {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
            last_time_point_start = time.time()

            event_group = list(group)
            logger.info("Starting stack for T=%d, P=%d", t_idx, p_idx)
            self._acquire_stack_at_position(event_group)

    def _acquire_stack_at_position(self, events: list[MDAEvent]):
        """
        Prepare hardware for a new position and acquire a Z-stack.
        This is called for every timepoint and position.
        """
        first_event = events[0]
        galvo_label = self.hw.galvo_a_label
        address = galvo_label.split(":")[-1]

        # 1. Ensure scanner is stopped before re-configuring.
        logger.debug(f"Issuing stop command to scanner card {address}.")
        send_tiger_command(self._mmc, f"{address}SCAN X=P")  # 'P' is the stop state
        time.sleep(0.2)  # Fixed delay to allow hardware to process the stop command.

        # 2. Move XY stage if necessary.
        if first_event.x_pos is not None and first_event.y_pos is not None:
            current_x, current_y = self._mmc.getXYPosition()
            # Use a small tolerance for float comparison
            if abs(current_x - first_event.x_pos) > 0.1 or abs(current_y - first_event.y_pos) > 0.1:
                logger.debug(f"Moving to XY: ({first_event.x_pos:.2f}, {first_event.y_pos:.2f})")
                self._mmc.setXYPosition(first_event.x_pos, first_event.y_pos)
                self._mmc.waitForDevice(self._mmc.getXYStageDevice())
            else:
                logger.debug("Already at target XY position.")

        # 3. Configure galvo for the scan at the current position.
        if self.settings:
            logger.info("Configuring galvo for Z-stack.")
            configure_galvo_for_hardware_timed_scan(self._mmc, self.settings, self.hw)
        else:
            logger.error("Settings not available, cannot configure galvo.")
            return

        # 4. Acquire the Z-stack.
        self._acquire_hardware_timed_z_stack(events)

    def _acquire_hardware_timed_z_stack(self, events: list[MDAEvent]):
        """
        Trigger and acquire a single, fully autonomous hardware-timed Z-stack.
        Assumes hardware (galvo, etc.) is already configured for this stack.
        """
        num_z = len(events)
        cam_label = self.hw.camera_a_label
        address = self.hw.galvo_a_label.split(":")[-1]

        # Set a timeout to ensure popNextImage blocks but doesn't hang forever
        exposure_ms = self.settings.camera_exposure_ms if self.settings else 10.0
        timeout_ms = int(exposure_ms + 5000)
        self._mmc.setTimeoutMs(timeout_ms)
        logger.debug(f"Set acquisition timeout to {timeout_ms} ms.")

        # Prime the camera to expect `num_z` frames
        self._mmc.startSequenceAcquisition(cam_label, num_z, 0, True)

        # Send the single 'SCAN' command to start the hardware sequence
        send_tiger_command(self._mmc, f"{address}SCAN")

        # Collect the images as they arrive by blocking until they are ready
        frames_collected = 0
        try:
            for i, event in enumerate(events):
                if not self._running:
                    logger.warning("Acquisition stopped mid-stack by user.")
                    send_tiger_command(self._mmc, f"{address}SCAN X=P")
                    break

                # This call will block until an image is available or the timeout is reached
                tagged_img = self._mmc.popNextTaggedImage()
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug(f"Frame collected: {event.index}")
                frames_collected += 1

        except RuntimeError as e:
            logger.error(f"Acquisition timed out waiting for image. Error: {e}")
        finally:
            # Ensure we stop the sequence acquisition for this stack
            if self._mmc.isSequenceRunning(cam_label):
                self._mmc.stopSequenceAcquisition(cam_label)
            logger.info(f"Z-stack for event {events[0].index} complete. Collected {frames_collected}/{num_z} frames.")

    def _get_z_step_size(self, z_plan) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        if z_plan and len(z_plan) > 1:
            positions = list(z_plan)
            return abs(positions[1] - positions[0])
        return 0.0

    def _get_time_interval_s(self, time_plan) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0


class CustomPLogicMDAEngine(MDAEngine):
    """
    Custom MDA engine for PLogic-driven SPIM Z-stacks.
    """

    def __init__(self):
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self.hw = HardwareConstants()
        self._worker: AcquisitionWorker | None = None
        self._thread: QThread | None = None

    def run(self, sequence: MDASequence):
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")
            self._mmc.mda.events.sequenceStarted.emit(sequence, {})
            self._worker = AcquisitionWorker(self._mmc, sequence)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            self._worker.frameReady.connect(self._on_frame_ready)
            self._thread.started.connect(self._worker.run)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine")
            self._mmc.run_mda(sequence)

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            result = current_focus_device == self.hw.plogic_focus_device_label
            return result
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _on_frame_ready(self, frame, event, meta):
        self._mmc.mda.events.frameReady.emit(frame, event, meta)

    def _on_acquisition_finished(self, sequence):
        logger.info("Custom MDA sequence finished. Cleaning up hardware state.")
        reset_camera_trigger_mode_internal(self._mmc, self.hw)
        disable_live_laser(self._mmc, self.hw)

        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._mmc.mda.events.sequenceFinished.emit(sequence)
        logger.info("Hardware and thread cleanup complete.")
