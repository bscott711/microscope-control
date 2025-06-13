# Detailed breakdown of plogic calls

The user action begins at 10:24:59.325965 when the "Test Acq" button is clicked. This single click initiates a cascade of commands sent to the ASI Tiger controller on COM4 to prepare the hardware for a fully automated, hardware-timed diSPIM acquisition sequence.

The process can be broken down into four main phases:

Initial Laser & Camera Setup: Activating the required laser lines.
Scanner & Timing Configuration: Programming the main SPIM controller (the scanner card) with all timing, delay, and movement parameters for the volume.
Logic Card Programming: Writing a specific, low-level hardware program to the PLogic card to ensure correct triggering and synchronization between the lasers and cameras.
Execution: A single command to start the pre-loaded hardware sequence.
Detailed Serial Command Breakdown
Below is a chronological table of every serial command sent to the Tiger controller (COM4) during this process, along with its meaning and purpose.

Note: In the ASI command syntax [Address] [Command] [Parameters], the address is a decimal number corresponding to the device's address on the controller's internal bus.

Timestamp (s) Serial Command Target Device (Address) Meaning and Purpose
Phase 1: Initial Laser & Camera Setup
10:24:59.331 6CCA X=30 PLogic Card (Addr 6) Sets the card to Preset 30. This corresponds to the Micro-Manager preset "All Lasers", activating the necessary output lines for illumination.
Phase 2: Scanner & Timing Configuration
10:25:01.901 3LED R=0 Scanner Card (Addr 3) Sets the BeamEnabled property to No (LED R=0). This ensures the laser beam is off while the scanner is being configured.
10:25:01.992 ! A B Scanner Card (Addr 3) HALT command for axes A and B (the galvos). This stops any existing motion before loading the new sequence.
10:25:02.024 3NR R=1 Scanner Card (Addr 3) Sets SPIMNumSlicesPerPiezo to 1. NR is the "Number of Repeats" command; the R parameter targets this specific setting.
10:25:02.053 3NV Z=0 Scanner Card (Addr 3) Sets SPIMDelayBeforeRepeat(ms) to 0. NV is the "New Value" command for timing parameters.
10:25:02.084 3NR F=1 Scanner Card (Addr 3) Sets SPIMNumRepeats to 1.
10:25:02.115 3NV Y=1 Scanner Card (Addr 3) Sets SPIMDelayBeforeSide(ms) to 1.
10:25:02.175 3RT F=29.25 Scanner Card (Addr 3) Sets the SPIMScanDuration(ms) to 29.25. RT is the "Repeat Time" command.
10:25:02.206 3NR Y=10 Scanner Card (Addr 3) Sets the SPIMNumSlices to 10. This defines the size of the Z-stack.
Phase 3: Logic Card Programming
10:25:02.361 6CCA X=12 PLogic Card (Addr 6) Sets the PLogic card to Preset 12. This preset is likely a template: "cell 10 = (TTL1 AND cell 8)". This prepares the card for further custom programming.
10:25:02.421 M E=6 PLogic Card (Addr 6) Move Pointer on axis E (the PLogic cell selector) to position 6. This selects logic cell #6 for editing.
10:25:02.758 6CCA Y=14 PLogic Card (Addr 6) Programs Cell #6: Sets the EditCellCellType to 14 - one shot (NRT).
10:25:02.972 6CCA Z=10 PLogic Card (Addr 6) Programs Cell #6: Sets the EditCellConfig to 10.
10:25:03.004 6CCB X=169 PLogic Card (Addr 6) Programs Cell #6: Sets EditCellInput1 to 169.
10:25:03.034 6CCB Y=233 PLogic Card (Addr 6) Programs Cell #6: Sets EditCellInput2 to 233.
10:25:03.064 6CCB Z=129 PLogic Card (Addr 6) Programs Cell #6: Sets EditCellInput3 to 129.
10:25:03.095 M E=7 PLogic Card (Addr 6) Move Pointer to position 7. This selects logic cell #7 for editing.
10:25:03.433 6CCA Y=14 PLogic Card (Addr 6) Programs Cell #7: Sets the EditCellCellType to 14 - one shot (NRT).
10:25:03.646 6CCA Z=1 PLogic Card (Addr 6) Programs Cell #7: Sets the EditCellConfig to 1.
10:25:03.677 6CCB X=134 PLogic Card (Addr 6) Programs Cell #7: Sets EditCellInput1 to 134.
10:25:03.708 6CCB Y=198 PLogic Card (Addr 6) Programs Cell #7: Sets EditCellInput2 to 198.
10:25:03.739 6CCB Z=129 PLogic Card (Addr 6) Programs Cell #7: Sets EditCellInput3 to 129.
10:25:03.769 6CCA X=3 PLogic Card (Addr 6) Sets the PLogic card to Preset 3, which is "cell 1 high". This likely arms the logic circuit after programming.
Phase 4: Execution
10:25:04.608 6CCA X=11 PLogic Card (Addr 6) Sets the PLogic card to Preset 11. This is the final state needed to correctly route triggers during the acquisition.
10:25:04.743 3SN Scanner Card (Addr 3) SCAN. This is the master command that initiates the entire pre-loaded hardware sequence. After this command is sent, the Tiger controller takes over completely, running the 10-slice volume scan using the timings programmed in the previous steps without further software intervention.

Export to Sheets
Summary of the Action
When the user clicks "Test Acq", the software doesn't just tell the camera to take pictures. It orchestrates a complex hardware sequence:

It first silences the scanner galvos and illumination beam.
It then sends a series of NR, NV, and RT commands to the scanner card, loading it with the high-level parameters of the acquisition (10 slices, 29.25ms slice duration, etc.).
Concurrently, it performs a detailed, low-level programming of the PLogic card by moving a pointer to specific logic cells and writing their type, configuration, and input values using CCA and CCB commands. This creates the hardware-level "glue" that ensures the camera triggers fire at the exact right moment relative to the laser and galvo motion.
Finally, with all hardware pre-programmed and ready, the software sends a single 3SN command. This is the "go" signal that tells the SPIM controller to execute the sequence it just learned. The controller then manages the entire 1.48-second acquisition independently, providing the speed and precision required for this imaging technique.
