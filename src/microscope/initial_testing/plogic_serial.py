import time

import serial


class PLogicControl:
    """
    Controls the ASI Tiger PLogic card for a galvo-based Z-stack using
    fast LED lasers and no mechanical shutter.
    """

    def __init__(self, port: str, baud_rate: int = 115200):
        """
        Initializes the PLogicControl.

        Args:
            port (str): The serial port of the Tiger controller (e.g., 'COM4').
            baud_rate (int): The baud rate for the serial connection.
        """
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        """Establishes a connection to the Tiger controller."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
            print(f"Connected to Tiger controller on {self.port}")
        except serial.SerialException as e:
            print(f"Error connecting to {self.port}: {e}")
            raise

    def disconnect(self):
        """Closes the connection to the Tiger controller."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("Disconnected from Tiger controller.")

    def _send_command(self, command: str):
        """
        Sends a command to the Tiger and returns the response.

        Args:
            command (str): The serial command to send.

        Returns:
            str: The controller's response.
        """
        if not self.ser:
            raise ConnectionError("Not connected to the Tiger controller.")

        print(f"Sending: {command}")
        self.ser.write(f"{command}\r".encode("ascii"))
        time.sleep(0.1)
        raw_response = self.ser.read_all()
        response = raw_response.decode("ascii").strip() if raw_response else ""
        print(f"Response: '{response}'")
        if ":A" not in response and "OK" not in response and response:
            if ":N" in response:
                print(f"ERROR: Command '{command}' failed with response '{response}'")
            else:
                print(f"Warning: Command '{command}' may not have been successful. Response: '{response}'")
        return response

    def setup_experiment(
        self,
        galvo_card_addr: str,
        galvo_axis: str,
        plogic_card_addr: str,
        plogic_axis_letter: str,
        z_step_um: float,
        num_slices: int,
        laser_duration_ms: float,
        camera_exposure_ms: float,
    ):
        """
        Configures the Tiger controller for a synchronized Z-stack experiment.

        Args:
            galvo_card_addr (str): Address of the galvo card.
            galvo_axis (str): Axis letter for the Z-scan (e.g., 'A').
            plogic_card_addr (str): Address of the PLogic card.
            plogic_axis_letter (str): Axis letter for the PLogic card (e.g., 'E').
            z_step_um (float): Step size for the Z-stack in micrometers.
            num_slices (int): Total number of slices in the stack.
            laser_duration_ms (float): Duration of the laser pulse.
            camera_exposure_ms (float): Camera exposure time.
        """
        # --- 1. Configure Galvo Card for Z-Stack ---
        print("\n--- Configuring Galvo Card for Z-Stack ---")
        z_step_units = z_step_um * 10
        self._send_command(f"{galvo_card_addr}ZS {galvo_axis}={z_step_units} Y={num_slices}")
        self._send_command(f"{galvo_card_addr}TTL X=4")  # TTL-triggered Z-stack mode
        # Set TTL output to generate a master trigger pulse for the PLogic card
        self._send_command(f"{galvo_card_addr}TTL Y=2")
        self._send_command(f"{galvo_card_addr}RT Y=1")  # 1ms trigger pulse

        # --- 2. Program PLogic Card for Timed Outputs ---
        print("\n--- Programming PLogic Card ---")
        trigger_source_addr = 41  # Backplane TTL0

        # PLogic evaluation cycle is 4kHz, so 1 tic = 0.25ms
        laser_duration_tics = int(laser_duration_ms / 0.25)
        camera_exposure_tics = int(camera_exposure_ms / 0.25)

        # Define PLogic cell assignments
        laser_one_shot_cell = 1
        camera_one_shot_cell = 2

        # BNC assignments on PLogic card
        camera_bnc, laser_bnc = 33, 37  # BNC1, BNC5

        # Program Laser One-Shot (no delay needed)
        self._program_one_shot(
            plogic_card_addr, plogic_axis_letter, trigger_source_addr, laser_one_shot_cell, laser_duration_tics
        )

        # Program Camera One-Shot (no delay needed)
        self._program_one_shot(
            plogic_card_addr, plogic_axis_letter, trigger_source_addr, camera_one_shot_cell, camera_exposure_tics
        )

        # --- 3. Route PLogic Outputs to BNCs ---
        print("\n--- Routing PLogic Outputs to BNCs ---")
        self._route_output(plogic_card_addr, plogic_axis_letter, laser_bnc, laser_one_shot_cell)
        self._route_output(plogic_card_addr, plogic_axis_letter, camera_bnc, camera_one_shot_cell)

        # --- 4. Save Settings to Non-Volatile Memory ---
        print("\n--- Saving Settings ---")
        self._send_command(f"{galvo_card_addr}SS Z")
        self._send_command(f"{plogic_card_addr}SS Z")

        print("\n--- Programming Complete ---")
        print("Tiger controller is configured for a shutterless Z-stack.")

    def _program_one_shot(self, plogic_addr, plogic_axis, trigger_addr, one_shot_cell, duration_tics):
        """Helper function to program a one-shot cell."""
        # Program One-Shot Cell (Type 14: non-retriggerable one-shot)
        self._send_command(f"{plogic_addr}M {plogic_axis}={one_shot_cell}")
        self._send_command(f"{plogic_addr}CCA Y=14")
        self._send_command(f"{plogic_addr}CCA Z={duration_tics}")
        # Trigger on rising edge (+128) of the master trigger
        # Use the internal 4kHz clock (address 192)
        self._send_command(f"{plogic_addr}CCB X={trigger_addr + 128} Y=192")

    def _route_output(self, plogic_addr, plogic_axis, bnc_addr, source_cell):
        """Helper function to route a cell output to a BNC."""
        self._send_command(f"{plogic_addr}M {plogic_axis}={bnc_addr}")
        # Set BNC to be a push-pull output (Type 2)
        self._send_command(f"{plogic_addr}CCA Y=2")
        # Set the source for the BNC to be our one-shot cell
        self._send_command(f"{plogic_addr}CCA Z={source_cell}")


if __name__ == "__main__":
    # --- Standalone Execution Example ---
    try:
        # Using a 'with' statement ensures the serial connection is closed properly
        with PLogicControl(port="COM4") as controller:
            controller.setup_experiment(
                galvo_card_addr="34",
                galvo_axis="A",
                plogic_card_addr="36",
                plogic_axis_letter="E",
                z_step_um=1.0,
                num_slices=150,
                laser_duration_ms=10.0,
                camera_exposure_ms=10.0,
            )
    except (ConnectionError, serial.SerialException) as e:
        print(f"\nOperation failed: {e}")
