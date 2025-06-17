# hardware/base_asi_commands.py
from __future__ import annotations

from typing import TYPE_CHECKING

from pymmcore_plus import CMMCorePlus

from .exceptions import ASIException

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


class BaseASICommands:
    """
    A base class for all ASI command modules.

    It provides a common `_send` method for serial communication
    and handles basic initialization and error handling.
    """

    def __init__(
        self,
        mmc: CMMCorePlus,
        command_device_label: str,
    ) -> None:
        """
        Initializes the base command layer.

        Args:
            mmc: The `CMMCorePlus` instance.
            command_device_label: The MMCore device label to which serial
                commands will be sent (e.g., the Tiger Hub or a specific device).
        """
        self._mmc = mmc
        self._command_device = command_device_label

    def _send(self, command: str) -> str:
        """Sends a command to the designated ASI device and returns the response."""
        self._mmc.setProperty(self._command_device, "SerialCommand", command)
        response = self._mmc.getProperty(self._command_device, "SerialResponse")

        # Check if the response indicates an error
        if response.startswith(":N"):
            # Extract the specific error code (e.g., ":N-1") from the response
            error_code = response.split(" ")[0]
            # Now, raise the exception with the correct arguments
            raise ASIException(code=error_code, command=command)

        return response
