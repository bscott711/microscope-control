import os
import time
import traceback

from pymmcore_plus import CMMCorePlus

# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- User Editable Parameters ---
clockFrequencyHz = 2  # Clock frequency in Hertz
clockDutyCycle = 0.5  # Should be between 0 and 1 exclusive

# --- PLogic Constants (Should not need editing unless hardware/config changes) ---
plcName = "PLogic:E:36"  # Device label for the PLogic card

# Property names
propPosition = "PointerPosition"
propCellType = "EditCellCellType"
propCellConfig = "EditCellConfig"
propCellInput1 = "EditCellInput1"
propCellInput2 = "EditCellInput2"
propUpdates = "EditCellUpdateAutomatically"
propSaveSettings = "SaveCardSettings"  # For saving to card

# Property values/modes
valNo = "No"
valYes = "Yes"
valOneShotNRT = "14 - one shot (NRT)"  # Non-ReTriggerable one-shot

# PLogic internal addresses/constants
addrInvert = 64  # Bitmask for inverting input
addrEdge = 128  # Bitmask for triggering on edge (vs level)
valSaveSettings = "Z - save settings to card (partial)"  # For saving to card
ticsPerSecond = 4000.0  # Internal PLogic clock frequency

# Cell addresses (arbitrarily chosen free cells, check PLogic manual/config)
# Using cells 1 and 2 as in the BeanShell script
addrDelayNRT = 1
addrOneShot = 2

addrCellAlwaysLow = 0  # PLogic cell 0 is typically GND/LOW
addrCellAlwaysHigh = 63  # PLogic cell 63 is typically VCC/HIGH

# BNC Output addresses (check PLogic manual/config)
# BNC 1 = 33, BNC 2 = 34, BNC 3 = 35, BNC 4 = 36
# BNC 5 = 37, BNC 6 = 38, # BNC 7 = 39, BNC 8 = 40

addrOutputBNC3 = 35  # Address for BNC output #3
addrOutputBNC = 40  # Address for BNC output #8


def program_plogic_clock(
    mmc_core: CMMCorePlus,
    frequency_hz: float,
    duty_cycle: float,
    output_bnc_address: int,
    plogic_device_label: str = plcName,
):
    """
    Programs the PLogic device to generate a clock signal on a specified BNC output.

    Args:
        mmc_core: The CMMCorePlus instance.
        frequency_hz: The desired clock frequency in Hertz.
        duty_cycle: The desired clock duty cycle (0 to 1, exclusive).
        output_bnc_address: The internal PLogic address for the target BNC output.
        plogic_device_label: The Micro-Manager device label for the PLogic card.
    """
    print(
        f"\nProgramming PLogic '{plogic_device_label}' for {frequency_hz} Hz clock ({duty_cycle * 100}% duty cycle) on BNC address {output_bnc_address}..."
    )

    if plogic_device_label not in mmc_core.getLoadedDevices():
        print(
            f"Error: PLogic device '{plogic_device_label}' not found in loaded devices."
        )
        return False

    if not 0 < duty_cycle < 1:
        print(
            f"Error: Duty cycle must be between 0 and 1 (exclusive). Got {duty_cycle}"
        )
        return False

    # Calculate the cycle period and high period in terms of PLC "tics" (4kHz)
    # Add 0.5 for rounding to the nearest integer tic
    clockPeriodTics = int(ticsPerSecond / frequency_hz + 0.5)
    clockHighTics = int(clockPeriodTics * duty_cycle + 0.5)

    if clockPeriodTics <= 1:
        print(
            f"Error: Calculated clock period ({clockPeriodTics} tics) is too short for {frequency_hz} Hz."
        )
        return False
    if clockHighTics <= 0 or clockHighTics >= clockPeriodTics:
        print(
            f"Error: Calculated clock high period ({clockHighTics} tics) is invalid for period {clockPeriodTics}."
        )
        return False

    actual_frequency = ticsPerSecond / clockPeriodTics
    actual_duty_cycle = clockHighTics / clockPeriodTics

    print(f"Calculated: Period = {clockPeriodTics} tics, High = {clockHighTics} tics.")
    print(
        f"Actual output: Frequency = {actual_frequency:.2f} Hz, Duty Cycle = {actual_duty_cycle * 100:.2f}%."
    )

    # Store original update setting
    valUpdatesOriginal = None
    try:
        valUpdatesOriginal = mmc_core.getProperty(plogic_device_label, propUpdates)
        # Turn off updates to speed communication during programming
        mmc_core.setProperty(plogic_device_label, propUpdates, valNo)
        print(
            f"Temporarily set '{propUpdates}' to '{valNo}'. Original was '{valUpdatesOriginal}'."
        )
        time.sleep(0.05)  # Short pause after setting property

        # --- Program Cell 1 (Delay NRT) ---
        print(f"Programming Cell {addrDelayNRT} (Delay NRT)...")
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(addrDelayNRT)
        )  # Position expects string
        mmc_core.setProperty(plogic_device_label, propCellType, valOneShotNRT)
        # Config for one-shot is the pulse duration - 1
        mmc_core.setProperty(
            plogic_device_label, propCellConfig, str(clockPeriodTics - 1)
        )
        # Input 1 & 2: Trigger on inverted edge (rising edge of clock), clock on every tic
        mmc_core.setProperty(
            plogic_device_label, propCellInput1, str(addrInvert + addrEdge)
        )
        mmc_core.setProperty(
            plogic_device_label, propCellInput2, str(addrInvert + addrEdge)
        )
        time.sleep(0.05)

        # --- Program Cell 2 (One Shot) ---
        print(f"Programming Cell {addrOneShot} (One Shot)...")
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(addrOneShot)
        )  # Position expects string
        mmc_core.setProperty(plogic_device_label, propCellType, valOneShotNRT)
        # Config for one-shot is the pulse duration
        mmc_core.setProperty(plogic_device_label, propCellConfig, str(clockHighTics))
        # Input 1: Triggered by Cell 1 (Delay NRT)
        mmc_core.setProperty(plogic_device_label, propCellInput1, str(addrDelayNRT))
        # Input 2: Clock on every tic
        mmc_core.setProperty(
            plogic_device_label, propCellInput2, str(addrInvert + addrEdge)
        )
        time.sleep(0.05)

        # --- Connect Cell 2 output to the specified BNC ---
        print(
            f"Connecting Cell {addrOneShot} output to BNC address {output_bnc_address}..."
        )
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(output_bnc_address)
        )  # Position expects string
        # Config for an output cell is the address of the cell whose output it should mirror
        mmc_core.setProperty(plogic_device_label, propCellConfig, str(addrOneShot))
        time.sleep(0.05)

        print("PLogic programming complete.")
        return True

    except Exception as e:
        print(f"Error programming PLogic: {e}")
        traceback.print_exc()
        return False

    finally:
        # Restore original update setting if it was retrieved
        if valUpdatesOriginal is not None:
            try:
                mmc_core.setProperty(
                    plogic_device_label, propUpdates, valUpdatesOriginal
                )
                print(f"Restored '{propUpdates}' to '{valUpdatesOriginal}'.")
            except Exception as e:
                print(f"Error restoring '{propUpdates}' to '{valUpdatesOriginal}': {e}")
                traceback.print_exc()


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


def stop_plogic_clock_output(
    mmc_core: CMMCorePlus,
    output_bnc_address: int,
    plogic_device_label: str = plcName,
):
    """
    Stops the clock output on the specified PLogic BNC by setting its source cell to 0.
    Cell 0 is typically an 'always off' or ground signal.

    Args:
        mmc_core: The CMMCorePlus instance.
        output_bnc_address: The internal PLogic address for the target BNC output.
        plogic_device_label: The Micro-Manager device label for the PLogic card.
    """
    print(
        f"\nAttempting to stop clock output on PLogic '{plogic_device_label}' BNC address {output_bnc_address}..."
    )
    if plogic_device_label not in mmc_core.getLoadedDevices():
        print(
            f"  Warning: PLogic device '{plogic_device_label}' not found. Cannot stop clock output."
        )
        return False

    valUpdatesOriginal = None
    try:
        valUpdatesOriginal = mmc_core.getProperty(plogic_device_label, propUpdates)
        mmc_core.setProperty(plogic_device_label, propUpdates, valNo)
        time.sleep(0.05)

        mmc_core.setProperty(plogic_device_label, propPosition, str(output_bnc_address))
        # Set the source of the BNC output to cell 0 (typically "always off" or ground)
        mmc_core.setProperty(
            plogic_device_label, propCellConfig, "0"
        )  # Cell 0 as string
        time.sleep(0.05)
        print(
            f"  Set BNC address {output_bnc_address} (cell {output_bnc_address}) config to '0' to stop output."
        )
        return True
    except Exception as e:
        print(f"  Error stopping PLogic clock output: {e}")
        traceback.print_exc()
        return False
    finally:
        if (
            valUpdatesOriginal is not None
            and plogic_device_label in mmc_core.getLoadedDevices()
        ):
            try:
                mmc_core.setProperty(
                    plogic_device_label, propUpdates, valUpdatesOriginal
                )
                print(
                    f"  Restored '{propUpdates}' to '{valUpdatesOriginal}' after attempting to stop clock."
                )
            except Exception as e_restore:
                print(f"  Error restoring '{propUpdates}' during stop: {e_restore}")


# --- Example Usage ---
if __name__ == "__main__":
    print("Running PLogic Clock Generator Script...")

    # Use a path relative to the project root, assuming this script is in src/microscope
    # Adjust this path if your config file is elsewhere
    cfg_path = "hardware_profiles/20250523-OPM.cfg"
    resolved_cfg_path = None
    is_plogic_loaded_at_start = False  # Flag to track if PLogic was successfully loaded

    # Attempt to resolve relative config path
    if not os.path.isabs(cfg_path):
        script_dir = os.path.dirname(__file__)
        potential_path_from_src_parent = os.path.join(script_dir, "..", "..", cfg_path)
        potential_path_from_cwd = cfg_path

        if os.path.exists(potential_path_from_src_parent):
            resolved_cfg_path = os.path.abspath(potential_path_from_src_parent)
            print(f"Resolved relative config path to: {resolved_cfg_path}")
        elif os.path.exists(potential_path_from_cwd):
            resolved_cfg_path = os.path.abspath(potential_path_from_cwd)
            print(f"Resolved relative config path (from CWD) to: {resolved_cfg_path}")
        else:
            print(
                f"Warning: Relative config path '{cfg_path}' not found easily. Trying as is."
            )
            resolved_cfg_path = cfg_path  # Try the path as given
    else:
        resolved_cfg_path = cfg_path

    try:
        # Load the Micro-Manager configuration
        print(f"Attempting to load configuration: {resolved_cfg_path}")
        if mmc.systemConfigurationFile() != resolved_cfg_path:
            mmc.loadSystemConfiguration(resolved_cfg_path)
            print(f"Successfully loaded configuration: {mmc.systemConfigurationFile()}")
        else:
            print(f"Configuration '{resolved_cfg_path}' already loaded.")

        # Verify PLogic device is loaded
        if plcName not in mmc.getLoadedDevices():
            raise RuntimeError(
                f"PLogic device '{plcName}' not found after loading configuration."
            )
        is_plogic_loaded_at_start = True  # Set flag
        print(f"PLogic device '{plcName}' found.")

        # Set BNC3 (addrOutputBNC3) HIGH on script start
        print(
            f"\nSetting BNC {addrOutputBNC3} (Global Shutter) to HIGH on script start..."
        )
        if not set_plogic_bnc_state_and_save(
            mmc, addrOutputBNC3, "high", verbose=False
        ):
            print(f"Warning: Failed to set BNC {addrOutputBNC3} HIGH on startup.")
        else:
            print(f"BNC {addrOutputBNC3} set HIGH.")

        # Program the clock
        success = program_plogic_clock(
            mmc,
            clockFrequencyHz,
            clockDutyCycle,
            addrOutputBNC,  # Output to BNC
            plcName,
        )

        if success:
            print(
                "\nPLogic programmed successfully. The clock signal should now be active on BNC 8."
            )
            print(
                "You may need to keep this script or your main application running for the clock to persist."
            )
            print("Press Enter to stop clock, unload devices, and exit.")
            input()  # Wait for user input

        else:
            print("\nFailed to program PLogic.")

    except FileNotFoundError:
        print(f"Error: Configuration file not found at {resolved_cfg_path}")
    except RuntimeError as e:
        print(f"Initialization or device error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()

    finally:
        # Attempt to stop the clock output before unloading devices
        if is_plogic_loaded_at_start:  # Only try if PLogic was loaded
            # Stop the clock if it was running on addrOutputBNC
            # This also sets addrOutputBNC's source to cell 0.
            stop_plogic_clock_output(mmc, addrOutputBNC, plcName)

            # Explicitly set BNC3 (addrOutputBNC) to LOW and save this state.
            print(
                f"\nSetting BNC {addrOutputBNC} (Global Shutter) to LOW and saving settings on exit..."
            )
            set_plogic_bnc_state_and_save(mmc, addrOutputBNC3, "low", verbose=False)

        # Clean up MMCore
        print("\nUnloading all devices and resetting MMCore...")
        mmc.unloadAllDevices()
        mmc.reset()  # Use reset() for a more complete cleanup if needed
        print("Cleanup complete.")
        print("PLogic Clock Generator Script finished.")
