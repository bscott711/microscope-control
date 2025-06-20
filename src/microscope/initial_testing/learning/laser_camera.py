# filename: final_validate_script_v7.py
"""
FINAL v7 Phase 1: Complete Hardware Validation (Corrected `scanv` Call)

This script corrects a bug in the call to `box.scanv` by providing the
required `scan_start_mm` and `scan_stop_mm` arguments, resolving the static
analysis error.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus
from tigerasi.tiger_controller import TigerController

# --- Configuration (with separate cells for Laser and Camera) ---
CONFIG = {
    "mmc_config_file": "C:/path/to/your/hardware_profiles/20250523-OPM.cfg",
    "com_port": "COM4",  # <-- IMPORTANT: SET YOUR COM PORT
    "plogic_card_address": "36",
    # Device labels
    "camera_device_label": "Camera-1",
    "galvo_z_axis": "V",
    "galvo_y_axis": "Y",
    # PLogic settings now with two distinct action cells
    "plogic_galvo_trigger_ttl_addr": 43,
    "plogic_4khz_clock_addr": 192,
    "plogic_laser_action_cell": 10,
    "plogic_camera_action_cell": 11,
    "plogic_laser_preset_num": 5,  # Preset that routes action to laser TTL
    "plogic_camera_preset_num": 5,  # Assumed same or similar preset for camera
    # Acquisition settings
    "num_slices": 5,
    "exposure_time_ms": 10.0,
    # System clock
    "clock_frequency_hz": 4000,
}


# --- PLogic Cell Type Codes ---
class PLogicCellType:
    """Cell type codes for the 'CCA Y=<code>' command."""

    ONE_SHOT_NON_RETRIGGERABLE = 14


# --- Helper Function ---
def program_plogic_cell(
    box: TigerController,
    plogic_addr: str,
    cell_num: int,
    cell_type: int,
    cell_config: int,
    preset: int,
    inputs: dict[str, int],
):
    """
    Programs a single PLogic cell using the specified procedural logic.
    """
    logging.info(
        f"  Programming Cell {cell_num}: Preset={preset}, Type={cell_type}, Config={cell_config}, Inputs={inputs}"
    )
    # Step 1: Move pointer to the target cell
    box.send(f"M E={cell_num}")
    # Step 1a: Set the preset that defines the cell's core output action
    box.send(f"{plogic_addr}CCA X={preset}")
    # Step 2: Set the cell type (e.g., one-shot pulse)
    box.send(f"{plogic_addr}CCA Y={cell_type}")
    # Step 3: Set the cell configuration (e.g., duration in ticks)
    box.send(f"{plogic_addr}CCA Z={cell_config}")
    # Step 4: Set the cell inputs that trigger the action
    inputs_str = " ".join([f"{key}={val}" for key, val in inputs.items()])
    box.send(f"{plogic_addr}CCB {inputs_str}")


# --- Main Script ---
def main():
    """Main validation function."""
    print("--- FINAL v7 Phase 1: Two-Cell Logic Validation ---")
    mmc = CMMCorePlus.instance()
    box = None
    original_camera_trigger_mode = ""
    cam_label = CONFIG["camera_device_label"]

    try:
        # --- 1. System & Camera Setup (pymmcore-plus) ---
        print(f"Loading Micro-Manager config: {CONFIG['mmc_config_file']}...")
        mmc.loadSystemConfiguration(CONFIG["mmc_config_file"])
        original_camera_trigger_mode = mmc.getProperty(cam_label, "TriggerMode")
        print(f"Setting camera to Level Trigger mode (was '{original_camera_trigger_mode}')...")
        mmc.setProperty(cam_label, "TriggerMode", "Level")

        # --- 2. Tiger Controller Connection (tigerasi) ---
        print(f"Connecting to Tiger Controller on {CONFIG['com_port']}...")
        box = TigerController(CONFIG["com_port"])
        print("Tiger connection successful.")

        # --- 3. Calculate and Program PLogic with Two Cells ---
        print("\n--- Configuring PLogic Card with Two-Cell Logic ---")
        plogic_addr = CONFIG["plogic_card_address"]
        pulses_per_ms = CONFIG["clock_frequency_hz"] / 1000.0
        duration_ticks = int(CONFIG["exposure_time_ms"] * pulses_per_ms)

        # Define the trigger input, which is the same for both cells
        trigger_inputs = {
            "X": CONFIG["plogic_galvo_trigger_ttl_addr"],
            "Y": CONFIG["plogic_4khz_clock_addr"],
        }

        # Program the LASER Action Cell (e.g., Cell 10)
        program_plogic_cell(
            box=box,
            plogic_addr=plogic_addr,
            cell_num=CONFIG["plogic_laser_action_cell"],
            preset=CONFIG["plogic_laser_preset_num"],
            cell_type=PLogicCellType.ONE_SHOT_NON_RETRIGGERABLE,
            cell_config=duration_ticks,
            inputs=trigger_inputs,
        )

        # Program the CAMERA Action Cell (e.g., Cell 11)
        program_plogic_cell(
            box=box,
            plogic_addr=plogic_addr,
            cell_num=CONFIG["plogic_camera_action_cell"],
            preset=CONFIG["plogic_camera_preset_num"],
            cell_type=PLogicCellType.ONE_SHOT_NON_RETRIGGERABLE,
            cell_config=duration_ticks,
            inputs=trigger_inputs,
        )

        print("PLogic programming complete.")

        # --- 4. Configure and Execute Galvo SPIM Scan ---
        print("\nConfiguring and starting Galvo SPIM scan...")
        box.setup_scan(
            fast_axis=CONFIG["galvo_z_axis"],
            slow_axis=CONFIG["galvo_y_axis"],
            wait=True,
        )

        # CORRECTED LINE: Provide the required arguments for the slow axis.
        # For our 1D Z-scan, the slow axis is a dummy, so we define a scan
        # of zero length (start=0, stop=0) but provide the critical line_count.
        box.scanv(
            scan_start_mm=0,
            scan_stop_mm=0,
            line_count=CONFIG["num_slices"],
            wait=True,
        )

        print("\n--- EXECUTION ---")
        print("VALIDATION STEP: Use a multi-channel oscilloscope.")
        print(
            "Probe the laser TTL output AND the camera TTL output. "
            "You should see two signals that rise and fall simultaneously "
            "for each of the Z-slices."
        )

        mmc.startSequenceAcquisition(cam_label, CONFIG["num_slices"], 0, True)
        box.start_scan()

        while mmc.isSequenceRunning(cam_label) or box.is_moving():
            print("Acquisition running...", end="\r")
            time.sleep(0.5)

        print("\nHardware sequence finished.")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        logging.error("Exception occurred", exc_info=True)
    finally:
        # --- 5. Cleanup ---
        print("\n--- Performing Cleanup ---")
        if box:
            box.stop_scan()
        if mmc.getLoadedDevices():
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            if original_camera_trigger_mode and mmc.hasProperty(cam_label, "TriggerMode"):
                print("Resetting camera trigger mode...")
                mmc.setProperty(cam_label, "TriggerMode", original_camera_trigger_mode)
            mmc.reset()
            print("System reset and unloaded.")

    print("\n--- FINAL v7 Validation Script Complete ---")


if __name__ == "__main__":
    main()
