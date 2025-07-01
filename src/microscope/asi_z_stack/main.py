# src/microscope/asi_z_stack/main.py
import sys

from pymmcore_gui import MicroManagerGUI
from pymmcore_plus import CMMCorePlus
from qtpy.QtWidgets import QApplication

from .asi_controller import (
    close_global_shutter,
    configure_plogic_for_dual_nrt_pulses,
    open_global_shutter,
)
from .common import AcquisitionSettings, HardwareConstants

# 1. Create the Qt Application instance.
app = QApplication(sys.argv)

# 2. Get and configure the CMMCorePlus singleton.
mmc = CMMCorePlus.instance()
HW = HardwareConstants()
try:
    mmc.loadSystemConfiguration(HW.cfg_path)
    print(f"Successfully loaded system configuration: {HW.cfg_path}")

    # 3. SET THE Z-STAGE DEVICE
    # This is the key step. We are telling the MDA engine to use your
    # Piezo/Galvo stage for all Z-moves.
    mmc.setFocusDevice(HW.piezo_a_label)
    print(f"Set Z-stage device to: {HW.piezo_a_label}")

except Exception as e:
    print(f"\n--- CONFIGURATION ERROR ---\n{e}\n---------------------------\n")
    print("Loading demo configuration instead.")
    mmc.loadSystemConfiguration()


# 4. Define the hardware setup and cleanup functions.
def _prepare_for_acquisition():
    """Program the PLogic card right before the MDA sequence starts."""
    print("--- SEQUENCE STARTED: Preparing hardware ---")
    settings = AcquisitionSettings(camera_exposure_ms=mmc.getExposure())
    settings.laser_trig_duration_ms = settings.camera_exposure_ms

    open_global_shutter(HW.plogic_label, HW.tiger_comm_hub_label, HW.plogic_always_on_cell, HW.plogic_bnc3_addr)
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
    """Reset hardware after the MDA sequence finishes."""
    print("--- SEQUENCE FINISHED: Cleaning up hardware ---")
    close_global_shutter(HW.plogic_label, HW.tiger_comm_hub_label, HW.plogic_bnc3_addr)
    print("--- Hardware cleanup complete ---")


# 5. Connect the functions to the MDA engine events.
mmc.mda.events.sequenceStarted.connect(_prepare_for_acquisition)
mmc.mda.events.sequenceFinished.connect(_cleanup_after_acquisition)

# 6. Directly instantiate the main GUI window.
main_win = MicroManagerGUI()

# 7. Show the window and start the application's event loop.
main_win.show()
app.exec()
