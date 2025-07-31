import logging
import time
from typing import Optional

# Import the specific GUI class for type casting
from pymmcore_gui import MicroManagerGUI
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.mda import MDAEngine
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, QThread, Signal  # type: ignore
from qtpy.QtWidgets import QApplication
from useq import (
    MDASequence,
    MultiPhaseTimePlan,
    TIntervalLoops,
    ZAboveBelow,
    ZRangeAround,
)

from .constants import HardwareConstants
from .hardware import (
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
    trigger_spim_scan_acquisition,
)
from .settings import AcquisitionSettings

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.propagate = False


class AcquisitionWorker(QObject):
    """
    Worker object for running hardware-timed acquisitions in a separate thread.

    Signals:
        frameReady (object, object, object): Emitted for every frame. The engine
                                              will decide whether to display it.
        acquisitionFinished (object): Emitted when the acquisition is finished.
    """

    frameReady = Signal(object, object, object)
    acquisitionFinished = Signal(object)

    def __init__(self, mmc: CMMCorePlus, sequence: MDASequence, handler=None, parent=None):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.handler = handler
        self.HW = HardwareConstants()
        self._running = True

    def stop(self):
        """Stop the acquisition."""
        self._running = False

    def run(self):
        """Execute a hardware-timed MDA sequence."""
        original_autoshutter = self._mmc.getAutoShutter()

        if not self.sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            return

        # --- Get sequence parameters ---
        num_z_slices = len(list(self.sequence.z_plan))
        num_timepoints = self.sequence.shape[0]
        interval_s = self._get_time_interval_s(self.sequence.time_plan)
        scan_duration_s = (num_z_slices * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        if num_timepoints > 1 and interval_s <= 0:
            logger.warning(
                "Acquisition has multiple timepoints but no interval is set. "
                "The hardware will acquire all timepoints as fast as possible."
            )
        elif num_timepoints > 1 and repeat_delay_s < 0:
            logger.warning(
                "The requested time interval (%.2fs) is shorter than the Z-stack "
                "duration (%.2fs). Subsequent timepoints will be acquired with "
                "minimal delay.",
                interval_s,
                scan_duration_s,
            )

        total_images_expected = num_z_slices * num_timepoints
        logger.info(
            "Starting hardware-timed series: %d timepoints, %d z-slices, %.2f ms interval",
            num_timepoints,
            num_z_slices,
            repeat_delay_ms,
        )

        try:
            # ----------------- ONE-TIME HARDWARE SETUP -----------------
            self._mmc.setAutoShutter(False)
            if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
                raise RuntimeError("Failed to set camera to external trigger mode")

            step_size = self._get_z_step_size(self.sequence.z_plan)
            settings = AcquisitionSettings(
                num_slices=num_z_slices,
                step_size_um=step_size,
                camera_exposure_ms=self._mmc.getExposure(),
            )
            configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)

            z_positions = list(self.sequence.z_plan)
            galvo_amplitude_deg = 0
            if len(z_positions) > 1:
                z_range = max(z_positions) - min(z_positions)
                galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg
                logger.info(
                    "Calculated galvo amplitude of %.4f deg for a Z-range of %.2f um.",
                    galvo_amplitude_deg,
                    z_range,
                )
            else:
                logger.info("Z-plan has fewer than 2 points. Setting galvo amplitude to 0.")

            configure_galvo_for_spim_scan(
                self._mmc,
                galvo_amplitude_deg,
                num_z_slices,
                num_repeats=num_timepoints,
                repeat_delay_ms=repeat_delay_ms,
                hw=self.HW,
            )
            logger.info("Hardware configured for full time-series.")
            # ---------------------------------------------------------

            self._mmc.startSequenceAcquisition(self.HW.camera_a_label, total_images_expected, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label)

            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for i in range(total_images_expected):
                if not self._running:
                    break
                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning():
                        logger.error(
                            "Camera sequence stopped before all frames were collected. "
                            "Expected: %d, Collected: %d",
                            total_images_expected,
                            i,
                        )
                        raise RuntimeError("Camera sequence stopped unexpectedly.")
                    time.sleep(0.01)

                tagged_img = self._mmc.popNextTaggedImage()
                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)

                # Save every frame directly in this thread
                if self.handler:
                    try:
                        self.handler.frameReady(tagged_img.pix, event, meta)
                        logger.debug(f"Frame saved: {event.index}")
                    except Exception as e:
                        logger.error(f"Error in data handler for event {event.index}: {e}")

                # Emit every frame for the viewer buffer and potential display update
                self.frameReady.emit(tagged_img.pix, event, meta)

            logger.info("Hardware-driven time-series complete.")

        except Exception as e:
            logger.error(f"Error during acquisition: {e}", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            if self.handler:
                self.handler.sequenceFinished(self.sequence)

            set_property(self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger")
            logger.info(f"Camera {self.HW.camera_a_label} reverted to Internal Trigger.")
            set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
            logger.info("SPIMState reset to Idle.")
            self._mmc.stopSequenceAcquisition()
            self._mmc.setAutoShutter(original_autoshutter)
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Custom PLogic Z-stack completed.")

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
    """Custom MDA engine for PLogic-driven SPIM Z-stacks."""

    def __init__(self):
        """Initialize the engine and fetch the CMMCorePlus instance."""
        self._mmc = CMMCorePlus.instance()
        super().__init__(self._mmc)
        self.HW = HardwareConstants()
        self._worker = None
        self._thread = None
        self.z_slice_for_viewer: Optional[int] = None
        self._viewer_connections_made = False
        self._viewer = None
        self._viewer_handler = None

    def set_z_slice_for_viewer(self, index_map: dict):
        """Slot to receive the z-slice index from the viewer's slider."""
        if "z" in index_map:
            new_index = index_map["z"]
            if self.z_slice_for_viewer != new_index:
                self.z_slice_for_viewer = new_index
                logger.debug(f"Viewer Z-slice selection updated to: {new_index}")

    def run(self, sequence: MDASequence, handler=None):
        """Run an MDA sequence, delegating to the correct method."""
        if self._should_use_plogic(sequence):
            logger.info("Running custom PLogic Z-stack sequence")

            # Set initial z-slice for viewer to the middle slice
            num_z_slices = len(list(sequence.z_plan)) if sequence.z_plan else 0
            self.z_slice_for_viewer = num_z_slices // 2 if num_z_slices > 0 else 0
            logger.info(f"Initial viewer Z-slice set to: {self.z_slice_for_viewer}")

            if not self._viewer_connections_made:
                self._connect_to_viewer()

            self._mmc.mda.events.sequenceStarted.emit(sequence, {})

            self._worker = AcquisitionWorker(self._mmc, sequence, handler=handler)
            self._thread = QThread()
            self._worker.moveToThread(self._thread)

            self._worker.frameReady.connect(self._on_frame_ready)
            self._thread.started.connect(self._worker.run)
            self._worker.acquisitionFinished.connect(self._on_acquisition_finished)

            self._thread.start()
        else:
            logger.info("Falling back to default MDA engine")
            self._mmc.run_mda(sequence)

    def _connect_to_viewer(self):
        """Find the main window and connect to the viewer's signals."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            logger.warning("No QApplication instance found, cannot connect viewer.")
            return

        main_win: Optional[MicroManagerGUI] = None
        for widget in app.topLevelWidgets():
            if isinstance(widget, MicroManagerGUI):
                main_win = widget
                break

        if not main_win:
            logger.warning("Could not find MicroManagerGUI window to connect viewer.")
            return

        viewer_manager = main_win._viewers_manager

        def on_viewer_created(viewer, sequence):
            logger.info(f"MDA Viewer created. Connecting Z-slider for sequence {str(sequence.uid)[:8]}.")
            self._viewer = viewer
            self._viewer_handler = viewer_manager._handler or viewer_manager._own_handler
            viewer.display_model.current_index.events.value.connect(self.set_z_slice_for_viewer)
            self.set_z_slice_for_viewer(viewer.display_model.current_index)

        viewer_manager.mdaViewerCreated.connect(on_viewer_created)
        self._viewer_connections_made = True
        logger.info("Engine is now listening for new MDA viewers.")

    def _should_use_plogic(self, sequence: MDASequence) -> bool:
        """Check if the Core Focus device is the designated Piezo stage."""
        try:
            current_focus_device = self._mmc.getProperty("Core", "Focus")
            result = current_focus_device == "PiezoStage:P:34"
            logger.debug(
                f"Checking Core Focus. Current: '{current_focus_device}'. "
                f"Required: 'PiezoStage:P:34'. Should use PLogic? {result}"
            )
            return result
        except Exception as e:
            logger.warning("Could not verify Core Focus device, falling back. Error: %s", e)
            return False

    def _on_frame_ready(self, frame, event, meta):
        """Slot to handle the frameReady signal from the worker."""
        # This method now handles both populating the viewer's data buffer
        # and selectively updating the viewer's display.

        # 1. Populate viewer buffer by calling its handler directly
        if self._viewer_handler:
            self._viewer_handler.frameReady(frame, event, meta)

        # 2. Conditionally update the viewer's display
        if self._viewer and event.index.get("z") == self.z_slice_for_viewer:
            self._viewer.display_model.current_index.update(event.index)

    def _on_acquisition_finished(self, sequence):
        """Slot to handle the acquisitionFinished signal from the worker."""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        self._thread = None
        self._worker = None
        self._viewer = None
        self._viewer_handler = None
        self._mmc.mda.events.sequenceFinished.emit(sequence)
