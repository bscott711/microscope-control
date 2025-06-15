import threading

import serial

from .exceptions import ASIException


class BaseHardwareController:
    """
    A base class providing robust, thread-safe serial communication
    for all ASI hardware controllers.
    """

    def __init__(self):
        # This threading.Event ensures only one command is sent at a time
        self._safe_to_write = threading.Event()
        self._safe_to_write.set()

    def _send_command(self, ser: serial.Serial, command: str) -> str:
        """
        Sends a command and waits for a response.

        Args:
            ser: The active serial port connection.
            command: The serial command string to send.

        Returns:
            The response from the controller.

        Raises:
            ASIException: If the controller returns an error code.
        """
        self._safe_to_write.wait()
        self._safe_to_write.clear()

        try:
            ser.reset_input_buffer()
            ser.write(f"{command}\r".encode("ascii"))
            print(f"Sent -> {command}")

            response = ser.readline().decode("ascii").strip()
            print(f"Recv <- '{response}'")

            if response.startswith(":N"):
                raise ASIException(response, command)

            return response
        finally:
            self._safe_to_write.set()
