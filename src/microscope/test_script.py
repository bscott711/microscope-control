import time

from pymmcore_plus import CMMCorePlus

from microscope.hardware import HardwareController
from microscope.settings import AcquisitionSettings, HardwareConstants

mmc = CMMCorePlus.instance()
const = HardwareConstants()
hw = HardwareController(mmc, const)

settings = AcquisitionSettings(
    num_slices=10,
    step_size_um=1.0,
    laser_trig_duration_ms=10.0,
    piezo_center_um=-31.0,
)

# Configure and trigger
hw.setup_for_acquisition(settings)
time.sleep(0.2)
hw.trigger_acquisition()

print("Triggered. Waiting 2 seconds...")
time.sleep(2)

print("Resetting...")
hw.final_cleanup(settings)
