# hardware/engine/plans.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from microscope.config import AcquisitionSettings, HardwareConstants
    from microscope.hardware.hal import HardwareAbstractionLayer


class AcquisitionPlan(ABC):
    """
    Abstract base class for an acquisition strategy.

    A plan defines the sequence of hardware configurations and actions
    required to perform a specific type of experiment.
    """

    @abstractmethod
    def pre_acquisition_setup(
        self,
        hal: HardwareAbstractionLayer,
        settings: AcquisitionSettings,
        hw_constants: HardwareConstants,
    ):
        """Configure all hardware for the start of the acquisition."""
        pass

    @abstractmethod
    def post_acquisition_cleanup(self, hal: HardwareAbstractionLayer):
        """Return all hardware to a safe, idle state."""
        pass


class GalvoPLogicMDA(AcquisitionPlan):
    """
    An acquisition plan for a fully autonomous, galvo-driven,
    hardware-timed multi-dimensional acquisition.
    """

    def pre_acquisition_setup(
        self,
        hal: HardwareAbstractionLayer,
        settings: AcquisitionSettings,
        hw_constants: HardwareConstants,
    ):
        """Configures PLogic, Galvo, and Camera for the MDA."""
        # Use individual checks to help the type checker narrow the types
        if not hal.camera or not hal.scanner or not hal.plogic:
            raise RuntimeError("Required hardware (Camera, Scanner, PLogic) not found.")

        print("INFO: Configuring hardware with GalvoPLogicMDA plan...")

        # 1. Configure PLogic
        hal.plogic.configure_for_mda(settings)

        # 2. Configure camera exposure by assigning to the .value attribute
        hal.camera.exposure.value = settings.camera_exposure_ms

        # 3. Configure Galvo scan pattern
        x_amplitude_mv = hw_constants.sheet_width_deg * hw_constants.slice_calibration_slope_um_per_deg
        y_amplitude_mv = settings.num_slices * settings.step_size_um

        hal.scanner.setup_raster_scan(
            x_amplitude_mv=x_amplitude_mv,
            y_amplitude_mv=y_amplitude_mv,
            scan_rate_hz=1 / (hw_constants.line_scan_duration_ms / 1000),
            num_lines=settings.num_slices,
            offset_mv=(hw_constants.sheet_offset_deg, settings.piezo_center_um),
        )

        # 4. Prepare camera for sequence acquisition
        total_frames = settings.num_slices * settings.time_points
        hal.camera.start_sequence_acquisition(num_images=total_frames)

        # 5. Start the galvo scan
        hal.scanner.start()

    def post_acquisition_cleanup(self, hal: HardwareAbstractionLayer):
        """Stop scanning and camera acquisition."""
        if hal.scanner:
            hal.scanner.stop()
        if hal.camera:
            hal.camera.stop_sequence_acquisition()
        print("INFO: Hardware cleanup complete.")
