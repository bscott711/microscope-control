# src/microscope/ui/__main__.py
import sys

from pymmcore_gui import MicroManagerGUI
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

from microscope.asi_z_stack.asi_controller import (
    close_global_shutter,
    configure_plogic_for_dual_nrt_pulses,
    open_global_shutter,
)
from microscope.asi_z_stack.common import AcquisitionSettings, HardwareConstants


def main():
    """Launch the Microscope Control GUI and connect hardware events."""
    app = QApplication(sys.argv)

    mmc = CMMCorePlus.instance()
    HW = HardwareConstants()
    try:
        mmc.loadSystemConfiguration(HW.cfg_path)
        print(f"Successfully loaded system configuration: {HW.cfg_path}")

    except Exception as e:
        print(f"\n--- CONFIGURATION ERROR ---\n{e}\n---------------------------\n")
        print("Loading demo configuration instead. The GUI will still open.")
        mmc.loadSystemConfiguration()

    # Define and connect hardware setup/cleanup functions
    def _prepare_for_acquisition():
        print("--- SEQUENCE STARTED: Preparing hardware ---")
        settings = AcquisitionSettings(camera_exposure_ms=mmc.getExposure())
        settings.laser_trig_duration_ms = settings.camera_exposure_ms

        open_global_shutter(
            HW.plogic_label,
            HW.tiger_comm_hub_label,
            HW.plogic_always_on_cell,
            HW.plogic_bnc3_addr,
        )
        configure_plogic_for_dual_nrt_pulses(
            settings,
            HW.plogic_label,
            HW.tiger_comm_hub_label,
            HW.plogic_laser_preset_num,
            HW.plogic_camera_cell,
            HW.pulses_per_ms,
            HW.plogic_4khz_clock_addr,
            HW.plogic_trigger_ttl_addr,
            HW.plogic_laser_on_cell,
        )
        print("--- Hardware ready for acquisition ---")

    def _cleanup_after_acquisition(sequence=None):
        print("--- SEQUENCE FINISHED: Cleaning up hardware ---")
        close_global_shutter(
            HW.plogic_label, HW.tiger_comm_hub_label, HW.plogic_bnc3_addr
        )
        print("--- Hardware cleanup complete ---")

    mmc.mda.events.sequenceStarted.connect(_prepare_for_acquisition)
    mmc.mda.events.sequenceFinished.connect(_cleanup_after_acquisition)

    # Instantiate and show the main GUI
    main_win = MicroManagerGUI()
    main_win.show()
    app.exec()


if __name__ == "__main__":
    main()
