# filename: final_validate_script_v18.py
"""
FINAL v18 Phase 1: Complete Hardware Validation (Card-Addressed Triggers)

This script corrects a deadlock bug by explicitly addressing the TTL trigger
and master RM commands to the PLogic card. This ensures the card is correctly
configured to listen for the ring buffer triggers and start the sequence.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus
from tigerasi.device_codes import RingBufferMode, TTLIn0Mode

# --- Configuration ---
CONFIG = {
    "mmc_config_file": "hardware_profiles/20250523-OPM.cfg",
    "tiger_comm_hub_label": "TigerCommHub",
    "camera_device_label": "Camera-1",
    "plogic_card_address": "36",
    # Ring Buffer and axis settings
    "galvo_z_axis": "A",
    # PLogic addresses and cell assignments
    "plogic_rb_trigger_addr": 1,
    "plogic_4khz_clock_addr": 192,
    "plogic_laser_action_cell": 10,
    "plogic_camera_action_cell": 11,
    "plogic_laser_output_addr": 45,
    "plogic_camera_output_addr": 44,
    # Acquisition settings
    "num_slices": 3,
    "exposure_time_ms": 10.0,
    "z_center_um": 50.0,
    "step_size_um": 1.0,
    # System clock
    "clock_frequency_hz": 4000,
    # Calibration
    "slice_calibration_um_per_axis_unit": 0.1,
}


# --- PLogic Cell Type Codes ---
class PLogicCellType:
    ONE_SHOT_NON_RETRIGGERABLE = 14


# --- Helper Functions ---
def send_tiger_command(mmc: CMMCorePlus, command: str):
    """Sends a raw serial command string to the Tiger controller."""
    hub_label = CONFIG["tiger_comm_hub_label"]
    mmc.setProperty(hub_label, "SerialCommand", command)
    time.sleep(0.05)


def program_plogic_output_cell(
    mmc: CMMCorePlus,
    cell_num: int,
    pulse_duration_ticks: int,
    trigger_input_addr: int,
    output_addr: int,
):
    """Programs a PLogic cell to fire a physical TTL output."""
    plogic_addr = CONFIG["plogic_card_address"]
    clock_addr = CONFIG["plogic_4khz_clock_addr"]
    logging.info(f"  Programming Output Cell {cell_num} for TTL Addr {output_addr}...")
    send_tiger_command(mmc, f"M E={cell_num}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Y={PLogicCellType.ONE_SHOT_NON_RETRIGGERABLE}")
    send_tiger_command(mmc, f"{plogic_addr}CCA Z={pulse_duration_ticks}")
    send_tiger_command(mmc, f"{plogic_addr}CCB X={trigger_input_addr} Y={clock_addr}")
    send_tiger_command(mmc, f"{plogic_addr}CCA F={output_addr}")


# --- Main Script ---
def main():
    """Main validation function."""
    print("--- FINAL v18 Phase 1: Card-Addressed Trigger Validation ---")
    mmc = CMMCorePlus.instance()
    original_camera_trigger_mode = ""
    cam_label = CONFIG["camera_device_label"]

    try:
        # --- 1. System & Camera Setup ---
        print(f"Loading Micro-Manager config: {CONFIG['mmc_config_file']}...")
        mmc.loadSystemConfiguration(CONFIG["mmc_config_file"])
        original_camera_trigger_mode = mmc.getProperty(cam_label, "TriggerMode")
        print(f"Setting camera to 'Level Trigger' mode (was '{original_camera_trigger_mode}')...")
        mmc.setProperty(cam_label, "TriggerMode", "Level Trigger")

        # --- 2. Calculate Parameters ---
        pulses_per_ms = CONFIG["clock_frequency_hz"] / 1000.0
        duration_ticks = int(CONFIG["exposure_time_ms"] * pulses_per_ms)
        z_center_units = CONFIG["z_center_um"] / CONFIG["slice_calibration_um_per_axis_unit"]
        step_size_units = CONFIG["step_size_um"] / CONFIG["slice_calibration_um_per_axis_unit"]
        num_slices = CONFIG["num_slices"]
        start_pos = z_center_units - (step_size_units * (num_slices - 1) / 2)
        z_positions = [int(round(start_pos + i * step_size_units)) for i in range(num_slices)]
        print(f"\nCalculated Z-Positions (axis units): {z_positions}")

        # --- 3. Program PLogic Card for Explicit Output Control ---
        print("\n--- Configuring PLogic Card for Direct TTL Output ---")
        program_plogic_output_cell(
            mmc=mmc,
            cell_num=CONFIG["plogic_laser_action_cell"],
            pulse_duration_ticks=duration_ticks,
            trigger_input_addr=CONFIG["plogic_rb_trigger_addr"],
            output_addr=CONFIG["plogic_laser_output_addr"],
        )
        program_plogic_output_cell(
            mmc=mmc,
            cell_num=CONFIG["plogic_camera_action_cell"],
            pulse_duration_ticks=duration_ticks,
            trigger_input_addr=CONFIG["plogic_rb_trigger_addr"],
            output_addr=CONFIG["plogic_camera_output_addr"],
        )
        print("PLogic programming complete.")

        # --- 4. Configure and Load Ring Buffer ---
        print("\nConfiguring and loading Ring Buffer...")
        z_axis = CONFIG["galvo_z_axis"]
        plogic_addr = CONFIG["plogic_card_address"]
        send_tiger_command(mmc, "RM X=0")
        send_tiger_command(mmc, f"RM Y={z_axis} F={RingBufferMode.TTL.value}")
        for pos in z_positions:
            send_tiger_command(mmc, f"LD {z_axis}={pos}")

        # == BUG FIX ==
        # The TTL command MUST be addressed to the PLogic card that will
        # be receiving the trigger signal.
        print(f"Arming PLogic card (addr {plogic_addr}) for Ring Buffer triggers...")
        ttl_command = f"{plogic_addr}TTL X={TTLIn0Mode.MOVE_TO_NEXT_ABS_POSITION.value}"
        send_tiger_command(mmc, ttl_command)
        print("Ring Buffer loaded and PLogic armed.")

        # --- 5. Execute Sequence ---
        print("\n--- EXECUTION ---")
        mmc.startSequenceAcquisition(cam_label, num_slices, 0, True)

        # == BUG FIX ==
        # The master trigger (RM) should also be addressed to the PLogic card
        # to ensure the correct module is triggered.
        print(f"Issuing master trigger (RM) to PLogic card {plogic_addr}...")
        send_tiger_command(mmc, f"{plogic_addr}RM")

        while mmc.isSequenceRunning(cam_label):
            time.sleep(0.5)

        images_received = mmc.getRemainingImageCount()
        for _ in range(images_received):
            mmc.popNextImage()
        print(f"\nHardware sequence finished. Final images received: {images_received}")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        logging.error("Exception occurred", exc_info=True)
    finally:
        # --- 6. Cleanup ---
        print("\n--- Performing Cleanup ---")
        if mmc.getLoadedDevices():
            send_tiger_command(mmc, "RM X=0")
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            if original_camera_trigger_mode and mmc.hasProperty(cam_label, "TriggerMode"):
                mmc.setProperty(cam_label, "TriggerMode", original_camera_trigger_mode)
            mmc.reset()
            print("System reset and unloaded.")

    print("\n--- FINAL v18 Validation Script Complete ---")


if __name__ == "__main__":
    main()
