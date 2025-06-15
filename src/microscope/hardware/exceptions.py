class ASIException(Exception):
    """Exception raised for errors from the ASI Tiger controller."""

    ERROR_CODES = {
        ":N-1": "Unknown Command",
        ":N-2": "Unrecognized Axis Parameter",
        ":N-3": "Missing parameters",
        ":N-4": "Parameter Out of Range",
        ":N-5": "Operation failed",
        ":N-6": "Undefined Error",
        ":N-7": "Invalid Card Address",
        ":N-21": "Serial Command Halted",
    }

    def __init__(self, code: str, command: str = ""):
        self.code = code
        self.command = command
        try:
            self.message = self.ERROR_CODES[code]
        except KeyError:
            self.message = f"Unknown error code: {code}"
        super().__init__(self.message)

    def __str__(self):
        return f"ASI Command '{self.command}' failed with error {self.code}: {self.message}"
