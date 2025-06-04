from pymmcore_plus import CMMCorePlus
import time
import os
import traceback

# Initialize global core instance
mmc = CMMCorePlus.instance()

# --- User Editable Parameters for BNC1 (Slow Pulse) ---
bnc1_frequency_hz = 50  # e.g., 50 Hz
bnc1_pulse_duration_ms = 10.0  # Duration of the high pulse in milliseconds

# --- User Editable Parameters for BNC2 (Fast Clock) ---
bnc2_frequency_hz = 100.0  # Clock frequency in Hertz
bnc2_duty_cycle = 0.5  # Should be between 0 and 1 exclusive

# --- PLogic Device Constants ---
plcName = "PLogic:E:36"  # Device label for the PLogic card

# Property names
propPosition = "PointerPosition"
propCellType = "EditCellCellType"
propCellConfig = "EditCellConfig"
propCellInput1 = "EditCellInput1"
propCellInput2 = "EditCellInput2"
propUpdates = "EditCellUpdateAutomatically"

# Property values/modes
valNo = "No"
valYes = "Yes"
valOneShotNRT = "14 - one shot (NRT)"  # Non-ReTriggerable one-shot

# PLogic internal addresses/constants
addrInvert = 64  # Bitmask for inverting input
addrEdge = 128  # Bitmask for triggering on edge (vs level)
ticsPerSecond = 4000.0  # Internal PLogic clock frequency

# BNC Output addresses (check PLogic manual/config)
# BNC 1 = 33, BNC 2 = 34, BNC 3 = 35, BNC 4 = 36, etc.
addrOutputBNC1 = 33  # Address for BNC output #1
addrOutputBNC2 = 34  # Address for BNC output #2

# Cell addresses for BNC1 clock (e.g., cells 3 and 4)
bnc1_addr_delay_nrt = 3
bnc1_addr_one_shot = 4

# Cell addresses for BNC2 clock (e.g., cells 1 and 2)
bnc2_addr_delay_nrt = 1
bnc2_addr_one_shot = 2


def program_plogic_clock(
    mmc_core: CMMCorePlus,
    clock_name: str,  # For logging
    frequency_hz: float,
    duty_cycle: float,
    delay_cell_addr: int,
    one_shot_cell_addr: int,
    output_bnc_address: int,
    plogic_device_label: str = plcName,
):
    """
    Programs the PLogic device to generate a clock signal on a specified BNC output
    using the provided cell addresses.

    Args:
        mmc_core: The CMMCorePlus instance.
        clock_name: A descriptive name for this clock (e.g., "BNC1 Clock").
        frequency_hz: The desired clock frequency in Hertz.
        duty_cycle: The desired clock duty cycle (0 to 1, exclusive).
        delay_cell_addr: PLogic cell address for the NRT delay (period).
        one_shot_cell_addr: PLogic cell address for the NRT one-shot (high time).
        output_bnc_address: The internal PLogic address for the target BNC output.
        plogic_device_label: The Micro-Manager device label for the PLogic card.
    """
    print(
        f"\nProgramming PLogic '{plogic_device_label}' for {clock_name}: {frequency_hz} Hz ({duty_cycle * 100:.3f}% duty) on BNC {output_bnc_address} using cells {delay_cell_addr},{one_shot_cell_addr}..."
    )

    if plogic_device_label not in mmc_core.getLoadedDevices():
        print(
            f"Error: PLogic device '{plogic_device_label}' not found in loaded devices."
        )
        return False

    if not 0 < duty_cycle < 1:
        print(
            f"Error: Duty cycle for {clock_name} must be between 0 and 1 (exclusive). Got {duty_cycle}"
        )
        return False

    # Calculate the cycle period and high period in terms of PLC "tics" (4kHz)
    # Add 0.5 for rounding to the nearest integer tic
    clockPeriodTics = int(ticsPerSecond / frequency_hz + 0.5)
    clockHighTics = int(clockPeriodTics * duty_cycle + 0.5)

    if clockPeriodTics <= 1:
        print(
            f"Error: Calculated clock period ({clockPeriodTics} tics) for {clock_name} is too short for {frequency_hz} Hz."
        )
        return False
    if clockHighTics <= 0 or clockHighTics >= clockPeriodTics:
        print(
            f"Error: Calculated clock high period ({clockHighTics} tics) for {clock_name} is invalid for period {clockPeriodTics}."
        )
        return False

    actual_frequency = ticsPerSecond / clockPeriodTics
    actual_duty_cycle = clockHighTics / clockPeriodTics

    print(
        f"  {clock_name} Calculated: Period = {clockPeriodTics} tics, High = {clockHighTics} tics."
    )
    print(
        f"  Actual output: Frequency = {actual_frequency:.2f} Hz, Duty Cycle = {actual_duty_cycle * 100:.2f}%."
    )

    # Store original update setting
    valUpdatesOriginal = None
    try:
        valUpdatesOriginal = mmc_core.getProperty(plogic_device_label, propUpdates)
        # Turn off updates to speed communication during programming
        mmc_core.setProperty(plogic_device_label, propUpdates, valNo)
        print(
            f"  Temporarily set '{propUpdates}' to '{valNo}'. Original was '{valUpdatesOriginal}'."
        )
        time.sleep(0.05)  # Short pause after setting property

        # --- Program Delay NRT Cell ---
        print(f"  Programming Cell {delay_cell_addr} (Delay NRT for {clock_name})...")
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(delay_cell_addr)
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

        # --- Program One Shot Cell ---
        print(f"  Programming Cell {one_shot_cell_addr} (One Shot for {clock_name})...")
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(one_shot_cell_addr)
        )  # Position expects string
        mmc_core.setProperty(plogic_device_label, propCellType, valOneShotNRT)
        # Config for one-shot is the pulse duration
        mmc_core.setProperty(plogic_device_label, propCellConfig, str(clockHighTics))
        # Input 1: Triggered by the Delay NRT Cell for this clock
        mmc_core.setProperty(plogic_device_label, propCellInput1, str(delay_cell_addr))
        # Input 2: Clock on every tic
        mmc_core.setProperty(
            plogic_device_label, propCellInput2, str(addrInvert + addrEdge)
        )
        time.sleep(0.05)

        # --- Connect One Shot output to the specified BNC ---
        print(
            f"  Connecting Cell {one_shot_cell_addr} output to BNC address {output_bnc_address} for {clock_name}..."
        )
        mmc_core.setProperty(
            plogic_device_label, propPosition, str(output_bnc_address)
        )  # Position expects string
        # Config for an output cell is the address of the cell whose output it should mirror
        mmc_core.setProperty(
            plogic_device_label, propCellConfig, str(one_shot_cell_addr)
        )
        time.sleep(0.05)

        print(f"PLogic programming for {clock_name} complete.")
        return True

    except Exception as e:
        print(f"Error programming PLogic for {clock_name}: {e}")
        traceback.print_exc()
        return False

    finally:
        # Restore original update setting if it was retrieved
        if valUpdatesOriginal is not None:
            try:
                mmc_core.setProperty(
                    plogic_device_label, propUpdates, valUpdatesOriginal
                )
                print(f"  Restored '{propUpdates}' to '{valUpdatesOriginal}'.")
            except Exception as e:
                print(f"Error restoring '{propUpdates}' to '{valUpdatesOriginal}': {e}")
                traceback.print_exc()


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
        print(f"  Error stopping PLogic clock output on BNC {output_bnc_address}: {e}")
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
                    f"  Restored '{propUpdates}' to '{valUpdatesOriginal}' after attempting to stop clock on BNC {output_bnc_address}."
                )
            except Exception as e_restore:
                print(f"  Error restoring '{propUpdates}' during stop: {e_restore}")


# --- Example Usage ---
if __name__ == "__main__":
    print("Running PLogic Dual Clock Generator Script...")

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

        # --- Program BNC1 Clock (Slow Pulse) ---
        # Calculate duty cycle for BNC1 based on pulse duration
        if bnc1_frequency_hz > 0:
            bnc1_period_s = 1.0 / bnc1_frequency_hz
            bnc1_pulse_duration_s = bnc1_pulse_duration_ms / 1000.0
            bnc1_duty_cycle = bnc1_pulse_duration_s / bnc1_period_s
            if not (0 < bnc1_duty_cycle < 1):
                # This might happen if pulse duration is longer than period
                print(
                    f"Warning: BNC1 calculated duty cycle ({bnc1_duty_cycle:.3f}) is >= 1. Setting to 0.999."
                )
                bnc1_duty_cycle = 0.999  # Cap duty cycle
            if bnc1_duty_cycle <= 0:
                raise ValueError(
                    f"BNC1 calculated duty cycle ({bnc1_duty_cycle:.3f}) is <= 0. Check frequency and pulse duration."
                )
        else:
            raise ValueError("BNC1 frequency must be greater than 0.")

        success_bnc1 = program_plogic_clock(
            mmc,
            "BNC1 Clock",
            bnc1_frequency_hz,
            bnc1_duty_cycle,
            bnc1_addr_delay_nrt,
            bnc1_addr_one_shot,
            addrOutputBNC1,  # Output to BNC 1
            plcName,
        )

        # --- Program BNC2 Clock (Fast Clock) ---
        success_bnc2 = program_plogic_clock(
            mmc,
            "BNC2 Clock",
            bnc2_frequency_hz,
            bnc2_duty_cycle,
            bnc2_addr_delay_nrt,
            bnc2_addr_one_shot,
            addrOutputBNC2,  # Output to BNC 2
            plcName,
        )

        if success_bnc1 and success_bnc2:
            print(
                "\nPLogic programmed successfully. Clock signals should be active on BNC1 and BNC2."
            )
            print("Press Enter to stop clocks, unload devices, and exit.")
            input()  # Wait for user input

        else:
            print("\nFailed to program one or both PLogic clocks.")

    except FileNotFoundError:
        print(f"Error: Configuration file not found at {resolved_cfg_path}")
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except RuntimeError as e:
        print(f"Initialization or device error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()

    finally:
        # Attempt to stop the clock outputs before unloading devices
        if is_plogic_loaded_at_start:  # Only try to stop if PLogic was loaded
            print("\nStopping clock outputs...")
            stop_plogic_clock_output(mmc, addrOutputBNC1, plcName)  # Stop BNC1
            stop_plogic_clock_output(mmc, addrOutputBNC2, plcName)  # Stop BNC2

        # Clean up MMCore
        print("\nUnloading all devices and resetting MMCore...")
        mmc.unloadAllDevices()
        mmc.reset()  # Use reset() for a more complete cleanup if needed
        print("Cleanup complete.")
        print("PLogic Dual Clock Generator Script finished.")
