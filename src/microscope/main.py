import logging
import sys

from microscope.controller import ApplicationController

# Set up logger
logger = logging.getLogger(__name__)
logger.propagate = False
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)


def main():
    """Initializes and runs the microscope control application."""
    # The ApplicationController now manages the QApplication lifecycle.
    sys.exit(ApplicationController.run())


if __name__ == "__main__":
    main()
