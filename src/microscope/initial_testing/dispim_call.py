import time
from pathlib import Path
from typing import TYPE_CHECKING

# Use TYPE_CHECKING to avoid a circular import and allow for type hints
if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


def run_dispim_test_acquisition(core: "CMMCorePlus"):
    """
    Executes a hardware-timed diSPIM test acquisition sequence.

    This function replicates the exact sequence of commands sent to the ASI
    Tiger controller as captured in the provided Micro-Manager log file when
    the user clicked "Test Acq".

    The sequence involves:
    1. Setting up cameras and lasers.
    2. Programming the ASI scanner card with SPIM parameters (timings, delays).
    3. Performing low-level programming of the ASI PLogic card to manage
       hardware triggers.
    4. Initiating and waiting for the hardware-timed acquisition to complete.
    5. Cleaning up and returning the system to a safe, idle state.

    Args:
        core: An active and initialized pymmcore_plus.CMMCorePlus instance.
    """
    # Define device names for clarity and easy modification
    camera1_device = "Camera-1"
    camera2_device = "Camera-2"
    scanner_device = "Scanner:AB:33"
    plogic_device = "PLogic:E:36"
    hub_device = "TigerCommHub"  # Hub for sending direct serial commands

    # Store initial state to restore it later in the finally block
    initial_auto_shutter = core.getAutoShutter()
    initial_exposure_cam1 = core.getExposure(camera1_device)
    initial_exposure_cam2 = core.getExposure(camera2_device)
    initial_trigger_mode_cam1 = core.getProperty(camera1_device, "TriggerMode")
    initial_trigger_mode_cam2 = core.getProperty(camera2_device, "TriggerMode")

    print("--- Starting diSPIM Test Acquisition ---")

    try:
        # =================================================================
        # Phase 1: Initial Laser & Camera Setup
        # Reference: Log time 10:24:59.331
        # =================================================================
        print("Phase 1: Configuring lasers and cameras...")

        # Turn off auto-shutter to allow for manual control during sequence
        core.setAutoShutter(False)

        # Set the laser preset to "488nm" from the "Lasers" group
        core.setConfig("Lasers", "488nm")

        # Set camera trigger modes for hardware triggering
        core.setProperty(camera1_device, "TriggerMode", "Edge Trigger")
        core.setProperty(camera2_device, "TriggerMode", "Edge Trigger")

        # Set camera exposures based on the log's calculated values
        core.setExposure(camera1_device, 11.95)
        core.setExposure(camera2_device, 11.95)
        core.waitForSystem()
        print("...Lasers and cameras configured.")

        # =================================================================
        # Phase 2: Scanner & Timing Configuration
        # Reference: Log time 10:25:01.901 - 10:25:02.298
        # =================================================================
        print("Phase 2: Programming scanner card...")
        core.setProperty(scanner_device, "BeamEnabled", "No")
        core.setProperty(scanner_device, "SPIMNumSlicesPerPiezo", 1)
        core.setProperty(scanner_device, "SPIMDelayBeforeRepeat(ms)", 0)
        core.setProperty(scanner_device, "SPIMNumRepeats", 1)
        core.setProperty(scanner_device, "SPIMDelayBeforeSide(ms)", 1)
        core.setProperty(scanner_device, "SPIMScanDuration(ms)", 29.25)
        core.setProperty(scanner_device, "SPIMNumSlices", 10)
        core.setProperty(scanner_device, "SPIMNumSides", 1)
        core.setProperty(scanner_device, "SPIMFirstSide", "A")
        core.setProperty(scanner_device, "SPIMPiezoHomeDisable", "No")
        core.setProperty(scanner_device, "SPIMInterleaveSidesEnable", "No")
        core.waitForDevice(scanner_device)
        print("...Scanner card programmed.")

        # =================================================================
        # Phase 3: Logic Card Programming
        # Reference: Log time 10:25:02.361 - 10:25:03.800
        # =================================================================
        print("Phase 3: Performing low-level programming of PLogic card...")

        # --- Program Logic Cell #6 ---
        core.setProperty(plogic_device, "PointerPosition", 6)
        core.setProperty(plogic_device, "EditCellCellType", "14 - one shot (NRT)")
        core.setProperty(plogic_device, "EditCellConfig", 10)
        core.setProperty(plogic_device, "EditCellInput1", 169)
        core.setProperty(plogic_device, "EditCellInput2", 233)
        core.setProperty(plogic_device, "EditCellInput3", 129)

        # --- Program Logic Cell #7 ---
        core.setProperty(plogic_device, "PointerPosition", 7)
        core.setProperty(plogic_device, "EditCellCellType", "14 - one shot (NRT)")
        core.setProperty(plogic_device, "EditCellConfig", 1)
        core.setProperty(plogic_device, "EditCellInput1", 134)
        core.setProperty(plogic_device, "EditCellInput2", 198)
        core.setProperty(plogic_device, "EditCellInput3", 129)

        # --- Arm the logic circuit by sending the raw serial command ---
        # This replaces `core.setProperty(plogic_device, "SetCardPreset", "3 - cell 1 high")`
        core.setProperty(hub_device, "SerialCommand", "6CCA X=3")
        core.waitForSystem()  # Wait for command to be processed
        print("...PLogic card programmed and armed.")

        # =================================================================
        # Phase 4: Execution
        # Reference: Log time 10:25:04.608 - 10:25:05.156
        # =================================================================
        print("Phase 4: Executing hardware-timed acquisition...")

        # --- Set final PLogic preset by sending the raw serial command ---
        # This replaces the failing call:
        # core.setProperty(plogic_device, "SetCardPreset", "11 - cell 10 = (TTL1 AND cell 8)")
        core.setProperty(hub_device, "SerialCommand", "6CCA X=11")

        # Start sequence acquisition on the cameras (10 frames)
        num_frames = 10
        core.startSequenceAcquisition(camera1_device, num_frames, 0, True)
        core.startSequenceAcquisition(camera2_device, num_frames, 0, True)

        # This is the master "GO" command.
        core.setProperty(scanner_device, "SPIMState", "Running")

        # Wait for the acquisition to complete
        while core.isSequenceRunning(camera1_device) or core.isSequenceRunning(camera2_device):
            time.sleep(0.1)

        print(f"...Acquisition of {num_frames * 2} images complete.")

    finally:
        # =================================================================
        # Phase 5: Cleanup
        # Reference: Log time 10:25:05.156 onwards
        # =================================================================
        print("Phase 5: Cleaning up and restoring initial state...")

        # Ensure sequence acquisition is stopped on both cameras
        if core.isSequenceRunning(camera1_device):
            core.stopSequenceAcquisition(camera1_device)
        if core.isSequenceRunning(camera2_device):
            core.stopSequenceAcquisition(camera2_device)

        # --- Set PLogic card to a safe, idle state via raw serial command ---
        # This replaces `core.setProperty(plogic_device, "SetCardPreset", "10 - cell 8 low")`
        core.setProperty(hub_device, "SerialCommand", "6CCA X=10")

        # Restore initial camera and shutter settings
        core.setAutoShutter(initial_auto_shutter)
        core.setProperty(camera1_device, "TriggerMode", initial_trigger_mode_cam1)
        core.setProperty(camera2_device, "TriggerMode", initial_trigger_mode_cam2)
        core.setExposure(camera1_device, initial_exposure_cam1)
        core.setExposure(camera2_device, initial_exposure_cam2)

        # Ensure the scanner is idle
        core.setProperty(scanner_device, "SPIMState", "Idle")

        core.waitForSystem()
        print("--- Sequence complete. System restored. ---")


# Example usage:
if __name__ == "__main__":
    from pymmcore_plus import CMMCorePlus

    try:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent.parent.parent
        config_file = project_root / "hardware_profiles" / "20250523-OPM.cfg"

        print(f"Loading configuration from: {config_file.resolve()}")

        core = CMMCorePlus()
        core.loadSystemConfiguration(str(config_file))

        print("Configuration loaded successfully.")

        run_dispim_test_acquisition(core)

    except FileNotFoundError:
        print(f"ERROR: Configuration file not found at {config_file.resolve()}")  # type: ignore
        print("Please ensure the file path is correct relative to the script location.")
    except Exception as e:
        print(f"An error occurred: {e}")
