# src/microscope/acquisition/worker.py
"""
Worker for running hardware-timed MDA acquisitions.
Runs in a separate thread and emits frames as they are collected.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, Signal  # type: ignore
from useq import (
    MDASequence,
    MultiPhaseTimePlan,
    TIntervalLoops,
    ZAboveBelow,
    ZRangeAround,
)

from microscope.hardware import (
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
    trigger_spim_scan_acquisition,
)
from microscope.model.hardware_model import AcquisitionSettings, HardwareConstants

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
        frameReady (object, object, object): Emitted when a new frame is ready.
                                              Provides (image, event, metadata).
        acquisitionFinished (object): Emitted when the acquisition is finished.
                                      Provides the sequence object.
    """

    frameReady = Signal(object, object, object)
    acquisitionFinished = Signal(object)

    def __init__(self, mmc: CMMCorePlus, sequence: MDASequence, parent=None):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
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
        # The controller delay is from the end of one scan to the start of the next.
        # We must subtract the time it takes to acquire one z-stack.
        scan_duration_s = (num_z_slices * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        # Add a warning if no interval is set for a multi-timepoint acquisition
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

            # Calculate the required galvo amplitude from the z-plan range
            z_positions = list(self.sequence.z_plan)
            if len(z_positions) > 1:
                z_range = max(z_positions) - min(z_positions)
                galvo_amplitude_deg = z_range / self.HW.slice_calibration_slope_um_per_deg
                logger.info(
                    "Calculated galvo amplitude of %.4f deg for a Z-range of %.2f um.",
                    galvo_amplitude_deg,
                    z_range,
                )
            else:
                galvo_amplitude_deg = 0
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

            # ---- SINGLE TRIGGER AND COLLECTION LOOP ----
            self._mmc.startSequenceAcquisition(self.HW.camera_a_label, total_images_expected, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label, self.HW)

            # The MDASequence is immutable, so we create a new sequence object
            # with the axis_order forced to match the hardware's physical
            # acquisition order (T -> P -> Z -> C).
            sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
            events = iter(sequence)

            for i in range(total_images_expected):
                if not self._running:
                    break
                while self._mmc.getRemainingImageCount() == 0:
                    if not self._mmc.isSequenceRunning():
                        raise RuntimeError("Camera sequence stopped unexpectedly.")
                    time.sleep(0.001)

                tagged_img = self._mmc.popNextTaggedImage()
                event = next(events)
                meta = frame_metadata(self._mmc, mda_event=event)
                self.frameReady.emit(tagged_img.pix, event, meta)
                logger.debug(f"Frame collected: {event.index}")

            logger.info("Hardware-driven time-series complete.")

        except Exception as _e:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            logger.info("Acquisition sequence finished. Cleaning up.")
            # Set camera back to internal trigger mode
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
