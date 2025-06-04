import os
import time
from pymmcore_plus import CMMCorePlus


def set_plogic_bnc_state_and_save(
    mmc_core: CMMCorePlus, bnc_address: int, state: str, verbose: bool = False
) -> bool:
    """
    Sets a specified PLogic BNC output to a given state (high or low)
    and saves the settings to the PLogic card. Simplified for speed
    and with a verbose option.

    Args:
        mmc_core: An initialized CMMCorePlus instance.
        bnc_address: The internal PLogic address for the target BNC output
                     (e.g., 33 for BNC1, 34 for BNC2, 35 for BNC3, etc.).
        state: The desired state for the BNC output, either "high" or "low".
        verbose: If True, prints detailed operational messages. Defaults to False.

    Returns:
        True if all operations were successful, False otherwise.
    """
    plc_name = "PLogic:E:36"
    prop_position = "PointerPosition"
    prop_cell_config = "EditCellConfig"
    prop_save_settings = "SaveCardSettings"

    val_save_settings = "Z - save settings to card (partial)"

    config_val_for_state: str
    descriptive_state_name: str

    if state.lower() == "high":
        config_val_for_state = "64"  # Assumed value for 'always high'
        descriptive_state_name = "high"
    elif state.lower() == "low":
        config_val_for_state = "0"  # Assumed value for 'always low' (mirrors Cell 0)
        descriptive_state_name = "low"
    else:
        print(
            f"Error: Invalid state '{state}' provided to set_plogic_bnc_state_and_save. "
            "Must be 'high' or 'low'."
        )
        return False

    # Validate bnc_address (PLogic typically has addresses for BNCs from 33 to 40 for BNC1-8)
    if not (33 <= bnc_address <= 40):  # Common range for BNC outputs 1-8
        print(
            f"Error: BNC address {bnc_address} is outside the typical range "
            "for PLogic BNC outputs (33-40). Cannot proceed."
        )
        return False  # Made this a hard error for safety

    if plc_name not in mmc_core.getLoadedDevices():
        print(f"Error: PLogic device '{plc_name}' not found in loaded devices.")
        return False

    success = False
    try:
        if verbose:
            print(
                f"Configuring PLogic output at address {bnc_address} "
                f"to be '{descriptive_state_name}'..."
            )

        # 1. Set PointerPosition to the target BNC output cell
        if verbose:
            print(
                f"  Setting PLogic '{prop_position}' to '{str(bnc_address)}' (for BNC at address {bnc_address})."
            )
        mmc_core.setProperty(plc_name, prop_position, str(bnc_address))
        time.sleep(0.05)  # Crucial small delay after changing pointer

        # 2. Set EditCellConfig for the BNC output.
        if verbose:
            print(
                f"  Setting PLogic '{prop_cell_config}' for BNC at address {bnc_address} to "
                f"'{config_val_for_state}' (for {descriptive_state_name} state)."
            )
        mmc_core.setProperty(plc_name, prop_cell_config, config_val_for_state)
        time.sleep(0.05)  # Crucial small delay after setting config

        # 3. Save the settings to the PLogic card
        if verbose:
            print(f"  Setting PLogic '{prop_save_settings}' to '{val_save_settings}'.")
        mmc_core.setProperty(plc_name, prop_save_settings, val_save_settings)

        if verbose:
            print("  Waiting for PLogic settings to save...")
        time.sleep(0.5)  # Delay for save operation to complete on hardware

        if verbose:
            print(
                f"Successfully configured PLogic BNC at address {bnc_address} to '{descriptive_state_name}' and saved settings."
            )
        success = True

    except Exception as e:
        # This error will always print
        print(
            f"Error during PLogic configuration for BNC at address {bnc_address} to '{descriptive_state_name}': {e}"
        )
        # For more detailed debugging:
        # import traceback
        # traceback.print_exc()
        success = False

    return success


if __name__ == "__main__":
    # Example usage (requires a running MMCore instance with PLogic configured)
    try:
        mmc = CMMCorePlus.instance()
        # Ensure your Micro-Manager configuration with PLogic:E:36 is loaded
        # This example assumes the config is in a 'hardware_profiles' subdirectory
        # relative to where the script is run, or an absolute path.
        script_dir = (
            os.path.dirname(__file__) if "__file__" in locals() else os.getcwd()
        )
        # A more robust way to find the config if your project structure is fixed:
        project_root = os.path.abspath(
            os.path.join(script_dir, "..", "..")
        )  # Adjust ".." as needed
        cfg_file = os.path.join(project_root, "hardware_profiles", "20250523-OPM.cfg")

        if not os.path.exists(cfg_file):
            print(f"Config file not found at: {cfg_file}")
            print("Please adjust 'cfg_file' path in the example or ensure it exists.")
        elif mmc.systemConfigurationFile() != cfg_file:
            print(f"Loading MM config: {cfg_file}")
            mmc.loadSystemConfiguration(cfg_file)
        else:
            print(f"MM config {cfg_file} already loaded.")

        if "PLogic:E:36" not in mmc.getLoadedDevices():
            print(
                "PLogic:E:36 device not found. Please load the correct Micro-Manager configuration."
            )
            print("Example usage will not run effectively.")
        else:
            print("PLogic device 'PLogic:E:36' found. Proceeding with example calls.")

            addr_bnc3 = 35  # PLogic address for BNC3
            addr_bnc8 = 40  # PLogic address for BNC8

            # --- Test with verbose=True ---
            print("\n--- Testing with verbose=True ---")
            print(f"Attempting to set BNC at address {addr_bnc3} HIGH (verbose)...")
            if set_plogic_bnc_state_and_save(mmc, addr_bnc3, "high", verbose=True):
                print(f"Successfully set BNC at address {addr_bnc3} to high.")
            else:
                print(f"Failed to set BNC at address {addr_bnc3} to high.")

            # --- Test with verbose=False (default) ---
            print("\n--- Testing with verbose=False (default) ---")
            print(f"Attempting to set BNC at address {addr_bnc8} HIGH (non-verbose)...")
            if set_plogic_bnc_state_and_save(
                mmc, addr_bnc8, "high"
            ):  # verbose is False by default
                print(
                    f"Call to set BNC at address {addr_bnc8} to high completed (check hardware)."
                )
            else:
                print(f"Failed to set BNC at address {addr_bnc8} to high.")

            # input("\nBNCs 3 and 8 should be high. Press Enter to set them low...")

            print("\n--- Setting BNCs low (verbose=True for one, False for other) ---")
            print(f"Attempting to set BNC at address {addr_bnc3} LOW (verbose)...")
            if set_plogic_bnc_state_and_save(mmc, addr_bnc3, "low", verbose=True):
                print(f"Successfully set BNC at address {addr_bnc3} to low.")
            else:
                print(f"Failed to set BNC at address {addr_bnc3} to low.")

            print(f"Attempting to set BNC at address {addr_bnc8} LOW (non-verbose)...")
            if set_plogic_bnc_state_and_save(mmc, addr_bnc8, "low", verbose=False):
                print(
                    f"Call to set BNC at address {addr_bnc8} to low completed (check hardware)."
                )
            else:
                print(f"Failed to set BNC at address {addr_bnc8} to low.")

            print("\nExample finished. BNCs 3 and 8 should now be low.")

    except ImportError:
        print("pymmcore_plus is not installed. This example cannot run.")
    except Exception as main_e:
        print(f"An error occurred in the example setup or execution: {main_e}")
        print(
            "Ensure Micro-Manager (pymmcore-plus) is properly initialized and configured, "
            "and the PLogic device is available."
        )
