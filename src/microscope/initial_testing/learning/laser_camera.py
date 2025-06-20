# filename: final_validate_script_v14.py
"""
FINAL v14 Phase 1: Complete Hardware Validation (Laser Enable Command)

This script adds the critical 'LED X=1' command to enable the logical laser
output before the scan begins. This should resolve the issue of the camera
firing while the laser does not.
"""

import logging
import time

from pymmcore_plus import CMMCorePlus

# --- Configuration ---
CONFIG = {
    "mmc_config_file": "hardware_profiles/20250523-OPM.cfg",
    "tiger_comm_hub_label": "TigerCommHub",
    "camera_device_label": "Camera-1",
    "scanner_card_address": "33",
    "scan_fast_axis": "A",
    "scan_slow_axis": "B",
    # Acquisition settings
    "num_slices": 3,
    "step_size_um": 1.0,
    "z_center_um": 50.0,
    "exposure_time_ms": 10.0,
    # Calibration
    "slice_calibration_um_per_deg": 100.0,
}


class ScanState:
    """State codes for the card-addressed 'SCAN X=...' command."""

    START = 83
    STOP = 80
    ARM = 97


def send_tiger_command(mmc: CMMCorePlus, command: str):
    """Sends a raw serial command string to the Tiger controller."""
    hub_label = CONFIG["tiger_comm_hub_label"]
    mmc.setProperty(hub_label, "SerialCommand", command)
    time.sleep(0.02)


# --- Main Script ---
def main():
    """Main validation function."""
    print("--- FINAL v14 Phase 1: Laser Enable Validation ---")
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

        # --- 2. Configure Galvo Scan & Pulse Durations ---
        print("\n--- Configuring SPIM Firmware via High-Level Commands---")
        scanner_addr = CONFIG["scanner_card_address"]
        num_slices = CONFIG["num_slices"]
        fast_axis = CONFIG["scan_fast_axis"]
        slow_axis = CONFIG["scan_slow_axis"]  # noqa: F841
        exposure_ms = CONFIG["exposure_time_ms"]

        # A) Calculate and set the physical scan dimensions
        total_scan_range_um = (num_slices - 1) * CONFIG["step_size_um"]
        scan_amplitude_deg = total_scan_range_um / CONFIG["slice_calibration_um_per_deg"]
        scan_offset_deg = 0

        send_tiger_command(mmc, f"{scanner_addr}SAA {fast_axis}={scan_amplitude_deg}")
        send_tiger_command(mmc, f"{scanner_addr}SAO {fast_axis}={scan_offset_deg}")

        # B) Set the number of slices for the SPIM routine
        send_tiger_command(mmc, f"{scanner_addr}NR Y={num_slices}")

        # C) Use the RT command to explicitly set laser and camera pulse durations
        print(f"Setting laser and camera pulse durations to {exposure_ms} ms using RT command...")
        send_tiger_command(mmc, f"{scanner_addr}RT R={exposure_ms} T={exposure_ms}")

        # D) == BUG FIX ==
        # Use the LED command to enable the "Side0" logical laser output.
        print("Enabling logical laser output...")
        send_tiger_command(mmc, f"{scanner_addr}LED X=1")

        print("SPIM firmware fully configured.")

        # --- 3. Execute Galvo SPIM Scan ---
        print("\n--- EXECUTION ---")
        print("Arming scanner...")
        send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.ARM}")

        mmc.startSequenceAcquisition(cam_label, num_slices, 0, True)

        print("Triggering armed scan...")
        send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.START}")

        while mmc.isSequenceRunning(cam_label):
            print(f"Acquisition running... Images in buffer: {mmc.getRemainingImageCount()}", end="\r")
            time.sleep(0.5)

        images_received = mmc.getRemainingImageCount()
        for _ in range(images_received):
            mmc.popNextImage()

        print(f"\nHardware sequence finished. Final images received: {images_received}")

    except Exception as e:
        print(f"\nAn error occurred: {e}")
        logging.error("Exception occurred", exc_info=True)
    finally:
        # --- 4. Cleanup ---
        print("\n--- Performing Cleanup ---")
        if mmc.getLoadedDevices():
            scanner_addr = CONFIG["scanner_card_address"]
            # Disable the logical laser and stop the scan
            send_tiger_command(mmc, f"{scanner_addr}LED X=0")
            send_tiger_command(mmc, f"{scanner_addr}SCAN X={ScanState.STOP}")
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            if original_camera_trigger_mode and mmc.hasProperty(cam_label, "TriggerMode"):
                print(f"Resetting camera trigger mode to '{original_camera_trigger_mode}'...")
                mmc.setProperty(cam_label, "TriggerMode", original_camera_trigger_mode)
            mmc.reset()
            print("System reset and unloaded.")

    print("\n--- FINAL v14 Validation Script Complete ---")


if __name__ == "__main__":
    main()
