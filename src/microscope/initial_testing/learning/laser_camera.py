# filename: final_validate_script_v11.py
"""
FINAL v11 Phase 1: Complete Hardware Validation (Correct Micro-Mirror Syntax)

This script implements the correct, card-addressed SCAN command syntax for a
micro-mirror (scanner) device. It sends state change commands directly to the
scanner's card address to start and stop the hardware-timed sequence.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus

# --- Configuration (Based on your .cfg file and feedback) ---
CONFIG = {
    "mmc_config_file": "hardware_profiles/20250523-OPM.cfg",
    # Device labels and addresses from your .cfg file
    "tiger_comm_hub_label": "TigerCommHub",
    "camera_device_label": "Camera-1",
    "scanner_card_address": "33",
    "plogic_card_address": "36",
    # PLogic settings
    "plogic_galvo_trigger_ttl_addr": 43, # This is the trigger from Scanner to PLogic
    "plogic_4khz_clock_addr": 192,
    "plogic_laser_action_cell": 10,
    "plogic_camera_action_cell": 11,
    "plogic_laser_preset_num": 5,
    "plogic_camera_preset_num": 5,
    # Acquisition settings
    "num_slices": 3,
    "exposure_time_ms": 10.0,
    # System clock
    "clock_frequency_hz": 4000,
}


# --- PLogic Cell Type Codes ---
class PLogicCellType:
    """Cell type codes for the 'CCA Y=<code>' command."""
    ONE_SHOT_NON_RETRIGGERABLE = 14

class ScanState:
    """State codes for the card-addressed 'SCAN X=...' command."""
    START = 83  # 'S'
    STOP = 80   # 'P'
    ARM = 97    # 'a'


# --- Helper Functions ---
def send_tiger_command(mmc: CMMCorePlus, command: str):
    """Sends a raw serial command string to the Tiger controller."""
    hub_label = CONFIG["tiger_comm_hub_label"]
    mmc.setProperty(hub_label, "SerialCommand", command)
    time.sleep(0.02)


def program_plogic_cell(
    mmc: CMMCorePlus, plogic_addr: str, cell_num: int, cell_type: int,
    cell_config: int, preset: int, inputs: dict[str, int],
):
    """Programs a single PLogic cell by sending serial commands via mmcore."""
    logging.info(
        f"  Programming Cell {cell_num}: Preset={preset}, Type={cell_type}, "
        f"Config={cell_config}, Inputs={inputs}"
    )
    send_tiger_command(mmc, f"M E={cell_num}")
    send_tiger_command(mmc, f"{plogic_addr}CCA X={preset}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Y={cell_type}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Z={cell_config}")
    inputs_str = " ".join([f"{key}={val}" for key, val in inputs.items()])
    send_tiger_command(mmc, f"{plogic_addr}CCB {inputs_str}")


# --- Main Script ---
def main():
    """Main validation function."""
    print("--- FINAL v11 Phase 1: Correct Micro-Mirror Syntax Validation ---")
    mmc = CMMCorePlus.instance()
    original_camera_trigger_mode = ""
    cam_label = CONFIG["camera_device_label"]

    try:
        # --- 1. System & Camera Setup ---
        print(f"Loading Micro-Manager config: {CONFIG['mmc_config_file']}...")
        mmc.loadSystemConfiguration(CONFIG["mmc_config_file"])
        original_camera_trigger_mode = mmc.getProperty(cam_label, "TriggerMode")
        print(f"Setting camera to Level Trigger mode (was '{original_camera_trigger_mode}')...")
        mmc.setProperty(cam_label, "TriggerMode", "Level Trigger")

        # --- 2. Calculate and Program PLogic ---
        print("\n--- Configuring PLogic Card via pymmcore-plus ---")
        plogic_addr = CONFIG["plogic_card_address"]
        pulses_per_ms = CONFIG["clock_frequency_hz"] / 1000.0
        duration_ticks = int(CONFIG["exposure_time_ms"] * pulses_per_ms)
        trigger_inputs = {
            "X": CONFIG["plogic_galvo_trigger_ttl_addr"],
            "Y": CONFIG["plogic_4khz_clock_addr"],
        }
        # Program the two action cells as before
        program_plogic_cell(
            mmc, plogic_addr, CONFIG["plogic_laser_action_cell"],
            PLogicCellType.ONE_SHOT_NON_RETRIGGERABLE, duration_ticks,
            CONFIG["plogic_laser_preset_num"], trigger_inputs
        )
        program_plogic_cell(
            mmc, plogic_addr, CONFIG["plogic_camera_action_cell"],
            PLogicCellType.ONE_SHOT_NON_RETRIGGERABLE, duration_ticks,
            CONFIG["plogic_camera_preset_num"], trigger_inputs
        )
        print("PLogic programming complete.")

        # --- 3. Configure Galvo Scan Parameters ---
        # For micro-mirror SPIM, parameters like slice count are set with SCANR/NR
        print("\nConfiguring Galvo scan parameters...")
        scanner_addr = CONFIG["scanner_card_address"]
        num_slices = CONFIG["num_slices"]
        send_tiger_command(mmc, f"{scanner_addr}NR Y={num_slices}")

        # --- 4. Execute Galvo SPIM Scan ---
        print("\n--- EXECUTION ---")
        # Arm the scanner first
        print("Arming scanner...")
        send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.ARM}")

        # Start camera sequence
        mmc.startSequenceAcquisition(cam_label, num_slices, 0, True)

        # Trigger the armed scan. This is the master command that starts everything.
        print("Triggering armed scan...")
        send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.START}")

        while mmc.isSequenceRunning(cam_label):
            print(f"Acquisition running... Images in buffer: {mmc.getRemainingImageCount()}", end='\r')
            time.sleep(0.5)

        print("\nHardware sequence finished.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        logging.error("Exception occurred", exc_info=True)
    finally:
        # --- 5. Cleanup ---
        print("\n--- Performing Cleanup ---")
        if mmc.getLoadedDevices():
            # Send the STOP command to the scanner card
            scanner_addr = CONFIG["scanner_card_address"]
            send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.STOP}")
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            if original_camera_trigger_mode and mmc.hasProperty(cam_label, "TriggerMode"):
                print(f"Resetting camera trigger mode to '{original_camera_trigger_mode}'...")
                mmc.setProperty(cam_label, "TriggerMode", original_camera_trigger_mode)
            mmc.reset()
            print("System reset and unloaded.")

    print("\n--- FINAL v11 Validation Script Complete ---")


if __name__ == "__main__":
    main()
