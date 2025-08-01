# src/microscope/core/engine/worker.py

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

from .. import (
    AcquisitionSettings,
    HardwareConstants,
    configure_galvo_for_spim_scan,
    configure_plogic_for_dual_nrt_pulses,
    set_camera_for_hardware_trigger,
    set_property,
    trigger_spim_scan_acquisition,
)

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
        self.HW = HardwareConstants()
        self._running = True

    def stop(self):
        """Request the acquisition to stop."""
        self._running = False

    def run(self):
        """Execute a hardware-timed MDA sequence."""
        original_autoshutter = self._mmc.getAutoShutter()
        if not self.sequence.z_plan:
            logger.error("PLogic acquisition requires a Z-plan.")
            self.acquisitionFinished.emit(self.sequence)
            return

        try:
            # --- Prepare Hardware ---
            self._mmc.setAutoShutter(False)
            if not set_camera_for_hardware_trigger(self._mmc, self.HW.camera_a_label):
                raise RuntimeError("Failed to set camera to external trigger mode.")

            settings = self._prepare_acquisition_settings()
            configure_plogic_for_dual_nrt_pulses(self._mmc, settings, self.HW)
            self._configure_galvo_from_sequence(settings.num_slices)

            # --- Run Acquisition ---
            total_images = len(list(self.sequence))
            self._mmc.startSequenceAcquisition(self.HW.camera_a_label, total_images, 0, True)
            trigger_spim_scan_acquisition(self._mmc, self.HW.galvo_a_label) # type: ignore

            # --- Collect Data ---
            events = iter(self.sequence)
            for i in range(total_images):
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

        except Exception:
            logger.error("Error during acquisition", exc_info=True)
        finally:
            self._cleanup(original_autoshutter)
            self.acquisitionFinished.emit(self.sequence)
            logger.info("Custom PLogic acquisition sequence finished.")

    def _prepare_acquisition_settings(self) -> AcquisitionSettings:
        """Create an AcquisitionSettings object from the MDASequence."""
        num_z = len(list(self.sequence.z_plan)) if self.sequence.z_plan else 0
        step_size = self._get_z_step_size()
        return AcquisitionSettings(
            num_slices=num_z,
            step_size_um=step_size,
            camera_exposure_ms=self._mmc.getExposure(),
        )

    def _configure_galvo_from_sequence(self, num_z_slices: int):
        """Configure the galvo based on the sequence parameters."""
        num_t = self.sequence.shape[0]
        interval_s = self._get_time_interval_s()
        scan_duration_s = (num_z_slices * self._mmc.getExposure()) / 1000.0
        repeat_delay_s = interval_s - scan_duration_s
        repeat_delay_ms = max(0, repeat_delay_s * 1000.0)

        z_positions = list(self.sequence.z_plan)  # type: ignore
        z_range = max(z_positions) - min(z_positions) if len(z_positions) > 1 else 0
        galvo_amplitude = z_range / self.HW.slice_calibration_slope_um_per_deg

        configure_galvo_for_spim_scan(
            self._mmc,
            galvo_amplitude_deg=galvo_amplitude,
            num_slices=num_z_slices,
            num_repeats=num_t,
            repeat_delay_ms=repeat_delay_ms,
            hw=self.HW,
        )

    def _cleanup(self, original_autoshutter: bool):
        """Restore hardware to a safe state after the acquisition."""
        set_property(self._mmc, self.HW.camera_a_label, "TriggerMode", "Internal Trigger")
        set_property(self._mmc, self.HW.galvo_a_label, "SPIMState", "Idle")
        self._mmc.stopSequenceAcquisition()
        self._mmc.setAutoShutter(original_autoshutter)
        logger.info("Hardware state restored after acquisition.")

    def _get_z_step_size(self) -> float:
        """Safely get the Z-step size from any Z-plan object."""
        z_plan = self.sequence.z_plan
        if isinstance(z_plan, (ZRangeAround, ZAboveBelow)):
            return z_plan.step
        if z_plan and len(z_plan) > 1:  # type: ignore
            positions = list(z_plan)
            return abs(positions[1] - positions[0])
        return 0.0

    def _get_time_interval_s(self) -> float:
        """Safely get the time interval in seconds from any TimePlan object."""
        time_plan = self.sequence.time_plan
        if isinstance(time_plan, TIntervalLoops):
            return time_plan.interval.total_seconds()
        if isinstance(time_plan, MultiPhaseTimePlan) and time_plan.phases:
            # Use the interval of the first phase for calculation
            first_phase = time_plan.phases[0]
            if isinstance(first_phase, TIntervalLoops):
                return first_phase.interval.total_seconds()
        return 0.0
