# src/microscope/acquisition/worker.py
"""
Worker for running hardware-timed MDA acquisitions.
Runs in a separate thread and emits frames as they are collected.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from pymmcore_plus import CMMCorePlus
from pymmcore_plus.metadata import frame_metadata
from qtpy.QtCore import QObject, Signal  # type: ignore
from useq import (
    AnyTimePlan,
    AnyZPlan,
    MDAEvent,
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

logger = logging.getLogger(__name__)


@dataclass
class TimingParams:
    """A simple container for calculated acquisition timing parameters."""

    num_z_slices: int
    num_timepoints: int
    repeat_delay_ms: float
    total_images: int


class AcquisitionWorker(QObject):
    """
    Worker object for running hardware-timed acquisitions in a separate thread.
    """

    # FIX: The metadata is a dict. The signal signature is now aligned
    # with the core pymmcore-plus frameReady signal.
    frameReady = Signal(object, MDAEvent, dict)
    acquisitionFinished = Signal(MDASequence)

    def __init__(
        self,
        mmc: CMMCorePlus,
        sequence: MDASequence,
        hw_constants: HardwareConstants,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._mmc = mmc
        self.sequence = sequence
        self.hw = hw_constants
        self._running = True

    def stop(self) -> None:
        """Flags the acquisition to stop gracefully."""
        logger.info("Stop requested for acquisition worker.")
        self._running = False

    def run(self) -> None:
        """
        Executes a hardware-timed MDA sequence by orchestrating the setup,
        execution, and cleanup phases.
        """
        self._original_autoshutter = self._mmc.getAutoShutter()
        self._mmc.setAutoShutter(False)
        logger.info("Starting acquisition worker.")

        try:
            params = self._calculate_timing_params()
            if not params:
                return

            if not self._configure_hardware(params):
                return

            self._execute_and_collect(params)

        except Exception as _:
            logger.critical("Acquisition failed due to an unexpected error.", exc_info=True)
        finally:
            self._cleanup_hardware()
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Acquisition worker finished.")

    def _calculate_timing_params(self) -> Optional[TimingParams]:
        """Calculates and validates timing parameters from the MDASequence."""
        if not self.sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            return None

        try:
            z_axis_index = self.sequence.axis_order.index("z")
            num_z = self.sequence.shape[z_axis_index]
        except ValueError:
            num_z = 1

        num_t = self.sequence.shape[0]
        interval_s = self._get_time_interval_s(self.sequence.time_plan)
        scan_duration_s = (num_z * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        if num_t > 1 and interval_s <= 0:
            logger.warning("Multi-timepoint acquisition has no interval; running ASAP.")
        elif num_t > 1 and repeat_delay_s < 0:
            logger.warning(
                "Time interval (%.2fs) is shorter than Z-stack duration (%.2fs). "
                "Acquiring subsequent timepoints with minimal delay.",
                interval_s,
                scan_duration_s,
            )

        logger.info(
            "Starting acquisition: %d timepoints, %d z-slices, %.2f ms interval.",
            num_t,
            num_z,
            repeat_delay_ms,
        )
        return TimingParams(
            num_z_slices=num_z,
            num_timepoints=num_t,
            repeat_delay_ms=repeat_delay_ms,
            total_images=num_z * num_t,
        )

    def _configure_hardware(self, params: TimingParams) -> bool:
        """Configures all hardware components for the full MDA sequence."""
        logger.info("Configuring hardware for MDA sequence...")
        z_plan = self.sequence.z_plan
        if not z_plan:
            logger.error("Z-plan is missing; cannot configure hardware.")
            return False

        if not set_camera_for_hardware_trigger(self._mmc, self.hw.camera_a_label):
            logger.error("Failed to set camera to external trigger mode.")
            return False

        settings = AcquisitionSettings(
            num_slices=params.num_z_slices,
            step_size_um=self._get_z_step_size(z_plan),
            camera_exposure_ms=self._mmc.getExposure(),
        )
        configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.hw)

        z_positions = list(z_plan)
        galvo_amplitude_deg = 0.0
        if len(z_positions) > 1:
            z_range = max(z_positions) - min(z_positions)
            galvo_amplitude_deg = z_range / self.hw.slice_calibration_slope_um_per_deg
            logger.info(
                "Calculated galvo amplitude: %.4f deg for Z-range of %.2f um.",
                galvo_amplitude_deg,
                z_range,
            )

        configure_galvo_for_spim_scan(
            self._mmc,
            galvo_amplitude_deg,
            params.num_z_slices,
            num_repeats=params.num_timepoints,
            repeat_delay_ms=params.repeat_delay_ms,
            hw=self.hw,
        )
        logger.info("Hardware configured successfully.")
        return True

    def _execute_and_collect(self, params: TimingParams) -> None:
        """Triggers the hardware sequence and collects incoming frames."""
        self._mmc.startSequenceAcquisition(self.hw.camera_a_label, params.total_images, 0, True)
        trigger_spim_scan_acquisition(self._mmc, self.hw)

        sequence = self.sequence.model_copy(update={"axis_order": ("t", "p", "z", "c")})
        events = iter(sequence)

        for _ in range(params.total_images):
            if not self._running:
                logger.info("Acquisition stopped by user.")
                break

            while self._mmc.getRemainingImageCount() == 0:
                if not self._mmc.isSequenceRunning():
                    logger.error("Camera sequence stopped unexpectedly.")
                    return
                time.sleep(0.001)

            tagged_img = self._mmc.popNextTaggedImage()
            event = next(events)
            # frame_metadata() returns a dict, which is the correct type for our signal.
            meta = frame_metadata(self._mmc, mda_event=event)
            self.frameReady.emit(tagged_img.pix, event, meta)
            logger.debug("Frame collected: %s", event.index)

    def _cleanup_hardware(self) -> None:
        """Resets hardware to a safe, idle state after acquisition."""
        logger.info("Cleaning up hardware state...")
        self._mmc.stopSequenceAcquisition()
        set_property(self._mmc, self.hw.camera_a_label, "TriggerMode", "Internal Trigger")
        set_property(self._mmc, self.hw.galvo_a_label, "SPIMState", "Idle")
        self._mmc.setAutoShutter(self._original_autoshutter)
        logger.info("Hardware cleanup complete.")

    def _get_z_step_size(self, z_plan: AnyZPlan) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step

        try:
            z_positions = list(z_plan)
            if len(z_positions) > 1:
                return abs(z_positions[1] - z_positions[0])
        except TypeError:
            pass  # This z_plan type is not iterable and has no .step.

        return 0.0

    def _get_time_interval_s(self, time_plan: Optional[AnyTimePlan]) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            return self._get_time_interval_s(time_plan.phases[0])
        return 0.0
