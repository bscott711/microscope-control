from pymmcore_plus import CMMCorePlus, DeviceType # Keep CMMCorePlus for non-mock path
from unittest.mock import MagicMock # For mock_hw mode
# Using RuntimeError as MMError is elusive and pymmcore-plus seems to handle/raise RuntimeErrors

# Default values - these should ideally come from a config or be passed appropriately
DEFAULT_MM_CONFIG_FILE = "path/to/your/mm_config.cfg" # Needs to be a real path for actual use
DEFAULT_STAGE_LABEL = "ASI XYStage" # Example, verify with your MM setup
ADAPTER_NAME = "ASIStage" # Example, verify with your MM setup for ASI
DEVICE_NAME = "XYStage"   # Example, verify with your MM setup for ASI

class Stage:
    """
    Represents the microscope stage and provides an interface for controlling it
    using pymmcore-plus.
    """

    def __init__(self,
                 mm_config_file: str = DEFAULT_MM_CONFIG_FILE,
                 stage_device_label: str = DEFAULT_STAGE_LABEL,
                 adapter_name: str = ADAPTER_NAME,
                 device_name: str = DEVICE_NAME,
                 mock_hw: bool = False # For testing without real hardware/config
                ):
        """
        Initializes the stage using pymmcore-plus.

        Args:
            mm_config_file: Path to the Micro-Manager hardware configuration file.
                            This is used if mock_hw is False.
            stage_device_label: The device label for the stage in Micro-Manager.
            adapter_name: The Micro-Manager adapter name for the ASI stage (e.g., "ASIStage").
            device_name: The device name for the ASI stage within the adapter (e.g., "XYStage").
            mock_hw: If True, simulates hardware initialization for testing purposes.
        """
        self.stage_device_label = stage_device_label
        self._current_position: float = 0.0  # Cache for current position
        self._is_jogging: bool = False # Represents if a jog command sequence is active
        self._jog_speed: float = 0.0 # Already initialized earlier, ensure no re-init here
        self._jog_direction: str = "" # Already initialized earlier

        self.mock_hw = mock_hw
        self.stage_device_label = stage_device_label # Store this regardless of mode
        self._current_position: float = 0.0
        self._is_jogging: bool = False
        # Note: self._jog_speed and self._jog_direction are already initialized above.

        if self.mock_hw:
            print(f"Stage '{self.stage_device_label}' initialized in MOCK hardware mode.")
            self.core = MagicMock() # No spec, more flexible for mock-only behavior
            self._current_position = 0.0
            self.core.getXPosition.return_value = self._current_position
            # Ensure all methods called by Stage methods exist on the MagicMock
            self.core.setXPosition.return_value = None
            self.core.setRelativeXPosition.return_value = None
            self.core.waitForDevice.return_value = None
            self.core.stop.return_value = None
            return

        # Proceed with actual hardware initialization if not mock_hw
        try:
            self.core = CMMCorePlus.instance()
            print(f"CMMCorePlus instance obtained: {self.core}")

            loaded_devices = self.core.getLoadedDevices()
            if self.stage_device_label not in loaded_devices:
                print(f"Loading device: {self.stage_device_label}, Adapter: {adapter_name}, Name: {device_name}")
                self.core.loadDevice(self.stage_device_label, adapter_name, device_name)
                self.core.initializeDevice(self.stage_device_label)
                print(f"Device {self.stage_device_label} initialized.")
            else:
                print(f"Device {self.stage_device_label} already loaded and presumably initialized.")

            device_type = self.core.getDeviceType(self.stage_device_label)
            if device_type not in [DeviceType.XYStage, DeviceType.Stage]:
                raise RuntimeError(f"Device {self.stage_device_label} is type {device_type}, not XYStage or Stage.")

            self._current_position = self.core.getXPosition(self.stage_device_label)
            print(f"Stage '{self.stage_device_label}' (HW) initialized. "
                  f"Initial X position: {self._current_position:.2f} um")

        except RuntimeError as e:
            print(f"Error initializing HW stage '{self.stage_device_label}': {e}")
            print("Falling back to MOCK hardware mode.")
            self.mock_hw = True
            self.core = MagicMock() # No spec for fallback mock core
            self._current_position = 0.0
            self.core.getXPosition.return_value = self._current_position
            self.core.setXPosition.return_value = None
            self.core.setRelativeXPosition.return_value = None
            self.core.waitForDevice.return_value = None
            self.core.stop.return_value = None
        except Exception as e:
            print(f"Unexpected error during HW stage '{self.stage_device_label}' initialization: {e}")
            print("Falling back to MOCK hardware mode.")
            self.mock_hw = True
            self.core = MagicMock() # No spec for fallback mock core
            self._current_position = 0.0
            self.core.getXPosition.return_value = self._current_position
            self.core.setXPosition.return_value = None
            self.core.setRelativeXPosition.return_value = None
            self.core.waitForDevice.return_value = None
            self.core.stop.return_value = None
            loaded_devices = self.core.getLoadedDevices()
            if self.stage_device_label not in loaded_devices:
                print(f"Attempting to load system configuration: {mm_config_file}")
                # If a full config file is provided and valid, it's often better to load it.
                # However, the prompt implies direct device loading.
                # For ASI stages, direct loading often requires serial port properties to be set first.
                # For simplicity, let's assume mm_config_file handles this if provided and valid.
                # If not, loadDevice might fail or need more properties.
                # self.core.loadSystemConfiguration(mm_config_file)
                # For now, trying direct load as per prompt structure, but this is tricky for ASI
                print(f"Loading device: {self.stage_device_label}, Adapter: {adapter_name}, Name: {device_name}")
                self.core.loadDevice(self.stage_device_label, adapter_name, device_name)
                # For ASI, you might need to set properties like serial port here before init.
                # e.g., self.core.setProperty(self.stage_device_label, "Port", "COM1")
                self.core.initializeDevice(self.stage_device_label)
                print(f"Device {self.stage_device_label} initialized.")
            else:
                print(f"Device {self.stage_device_label} already loaded.")

            # Ensure the stage is an XY stage type if we plan to use X/Y functions
            if self.core.getDeviceType(self.stage_device_label) not in [DeviceType.XYStage, DeviceType.Stage]:
                 raise MMError(f"Device {self.stage_device_label} is not of type XYStage or Stage.")

            self._current_position = self.core.getXPosition(self.stage_device_label)
            print(f"Stage '{self.stage_device_label}' initialized. "
                  f"Initial X position: {self._current_position:.2f} um")

        except RuntimeError as e: # Changed to RuntimeError
            print(f"Error initializing stage with pymmcore-plus: {e}")
            print("Stage will operate in MOCK hardware mode due to error.")
            self.mock_hw = True # Fallback to mock mode
            self.core = None    # Ensure core is None if init failed
            self._current_position = 0.0
        except Exception as e: # Catch other potential errors like file not found for config
            print(f"A non-MMError occurred during stage initialization: {e}")
            print("Stage will operate in MOCK hardware mode due to error.")
            self.mock_hw = True
            self.core = None
            self._current_position = 0.0


    def get_position(self) -> float:
        """
        Gets the current X position of the stage from the hardware.
        """
        if self.mock_hw or not self.core:
            # print(f"MOCK: Queried stage position: {self._current_position} um")
            return self._current_position

        try:
            pos = self.core.getXPosition(self.stage_device_label)
            self._current_position = pos # Update cache
            # print(f"HW: Queried stage position: {self._current_position:.2f} um")
            return pos
        except RuntimeError as e: # Changed to RuntimeError
            print(f"Error getting position for {self.stage_device_label}: {e}")
            # Fallback to cached position or handle error as appropriate
            return self._current_position


    def move_step(self, step_size: float, direction: str) -> None:
        """
        Moves the stage by a defined step in the X direction.
        """
        if self._is_jogging: # Conceptual check
            print("Conceptual jog is active. Call stop() before new move_step. For safety, stopping.")
            self.stop() # Stop any hardware action if stop() is robust

        if direction not in ["forward", "backward"]:
            print(f"Invalid direction: {direction}. Must be 'forward' or 'backward'.")
            return

        if step_size <= 0:
            print(f"Step size must be positive. Got: {step_size}")
            return

        if self.mock_hw or not self.core:
            print(f"MOCK: Attempting to move {direction} by {step_size} um...")
            if direction == "forward":
                self._current_position += step_size
            elif direction == "backward":
                self._current_position -= step_size
            print(f"MOCK: Move step complete. New position: {self._current_position:.2f} um")
            return

        try:
            current_x = self.core.getXPosition(self.stage_device_label)
            target_x = current_x + (step_size if direction == "forward" else -step_size)

            print(f"HW: Moving {self.stage_device_label} {direction} from {current_x:.2f} by {step_size} to {target_x:.2f} um...")
            self.core.setXPosition(self.stage_device_label, target_x)
            self.core.waitForDevice(self.stage_device_label) # Wait for move to complete
            self._current_position = self.core.getXPosition(self.stage_device_label)
            print(f"HW: Move complete. New position: {self._current_position:.2f} um")
        except RuntimeError as e: # Changed to RuntimeError
            print(f"Error during move_step for {self.stage_device_label}: {e}")
            # Update position cache even if error during move, to reflect last known state
            try:
                self._current_position = self.core.getXPosition(self.stage_device_label)
            except RuntimeError: # Changed to RuntimeError
                pass # If getting position also fails, keep last good cache


    def jog(self, speed: float, direction: str) -> None:
        """
        Performs a single small relative move for jogging in the X direction.
        The 'speed' parameter is used to determine the size of this small step.
        A true continuous jog would require repeated calls or hardware support.
        """
        if direction not in ["forward", "backward"]:
            print(f"Invalid jog direction: {direction}. Must be 'forward' or 'backward'.")
            return

        if speed <= 0:
            print(f"Jog speed must be positive for a move. Got: {speed}")
            return

        # This makes jog a single, small, speed-proportional step.
        # For example, if speed is "10 um/s", and widget calls this 10x per second,
        # then effective_step = speed / calls_per_second.
        # Here, we define one jog call makes a step of 'speed * 0.05' (e.g. 0.5um if speed is 10).
        # This scaling factor (0.05) is arbitrary and defines sensitivity.
        relative_step_size = speed * 0.05
        actual_move = relative_step_size if direction == "forward" else -relative_step_size

        self._is_jogging = True # Conceptual: a jog command has been issued
        self._jog_speed = speed
        self._jog_direction = direction

        if self.mock_hw or not self.core:
            print(f"MOCK: Jogging {direction} with effective step {actual_move:.2f} um (speed: {speed})...")
            self._current_position += actual_move
            print(f"MOCK: Jog move complete. New position: {self._current_position:.2f} um")
            # In mock, stop simply clears the flag.
            # self._is_jogging = False
            return

        try:
            print(f"HW: Jogging {self.stage_device_label} {direction} with relative step {actual_move:.2f} um (speed: {speed})...")
            self.core.setRelativeXPosition(self.stage_device_label, actual_move)
            self.core.waitForDevice(self.stage_device_label)
            self._current_position = self.core.getXPosition(self.stage_device_label)
            print(f"HW: Jog move complete. New position: {self._current_position:.2f} um")
        except RuntimeError as e: # Changed to RuntimeError
            print(f"Error during jog for {self.stage_device_label}: {e}")
            self._is_jogging = False # Ensure jogging state is reset on error
            try: # Try to update position cache
                self._current_position = self.core.getXPosition(self.stage_device_label)
            except RuntimeError: # Changed to RuntimeError
                pass
        # finally:
            # If jog is one-shot, then _is_jogging should be reset here.
            # However, the widget might rapidly call jog; stop() is the explicit way to clear it.
            # self._is_jogging = False


    def stop(self) -> None:
        """
        Stops any ongoing stage movement for the specified device.
        Also clears the conceptual 'jogging' state.
        """
        print(f"Attempting to stop stage: {self.stage_device_label if not self.mock_hw else 'MOCK'}")
        self._is_jogging = False # Clear conceptual jog state immediately

        if self.mock_hw or not self.core:
            print("MOCK: Stage stopped.")
            return

        try:
            self.core.stop(self.stage_device_label) # General stop command for the device
            print(f"HW: Stop command sent to {self.stage_device_label}.")
            # Update position after stop
            self._current_position = self.core.getXPosition(self.stage_device_label)
            print(f"HW: Position after stop: {self._current_position:.2f} um")
        except RuntimeError as e: # Changed to RuntimeError
            print(f"Error stopping stage {self.stage_device_label}: {e}")
            # Even if stop fails, try to get current position
            try:
                self._current_position = self.core.getXPosition(self.stage_device_label)
            except RuntimeError: # Changed to RuntimeError
                 pass # Keep last good cache


if __name__ == "__main__":
    # THIS EXAMPLE WILL LIKELY FAIL WITHOUT A REAL MM CONFIGURATION AND HARDWARE
    # OR WITHOUT A PROPERLY SET UP MOCK/DEMO CONFIG FOR pymmcore-plus.
    print("Running Stage example:")

    # To test with a mock:
    # stage = Stage(mock_hw=True)

    # To test with pymmcore-plus's demo config (if available and suitable):
    # cfg_path = "path_to_mm_config.cfg" # e.g. pymmcore_plus.core.DEFAULT_CONFIG_FILE if it points to a demo
    # If a demo config is used, ensure DEFAULT_STAGE_LABEL matches a stage in that demo config.
    # For instance, CMMCorePlus.demoConfig() creates a 'MMConfig_demo.cfg'
    # core_for_demo = CMMCorePlus.instance()
    # core_for_demo.loadSystemConfiguration(CMMCorePlus.demoConfig())
    # print("Demo devices:", core_for_demo.getLoadedDevices()) # Find a stage label
    # stage_label_demo = "XY" # This is often a label in demo configs
    # adapter_name_demo = "DemoCamera" # This is NOT a stage, find appropriate demo stage adapter/name
    # device_name_demo = "DXYStage"

    # For this example, we will default to mock_hw=True as no config is provided.
    # If you have a MM setup, provide your .cfg file and device label.
    print("Initializing Stage in MOCK mode for this example...")
    stage = Stage(mock_hw=True, stage_device_label="TestXYStage") # Using mock_hw=True

    print(f"Initial position: {stage.get_position():.2f} um")

    stage.move_step(5.0, "forward")
    print(f"Position after step forward: {stage.get_position():.2f} um")

    stage.move_step(2.0, "backward")
    print(f"Position after step backward: {stage.get_position():.2f} um")

    stage.move_step(-1.0, "forward") # Test invalid step (prints error, no move)
    stage.move_step(1.0, "somewhere") # Test invalid direction (prints error, no move)

    print("\n--- Jogging Test (conceptual) ---")
    stage.jog(20.0, "forward") # speed = 20um/s, actual_step = 20 * 0.05 = 1.0 um
    print(f"Position after one jog forward: {stage.get_position():.2f} um")
    # Simulate multiple jog calls by the widget
    stage.jog(20.0, "forward")
    print(f"Position after second jog forward: {stage.get_position():.2f} um")

    stage.stop() # Clears _is_jogging flag
    print(f"Position after stopping: {stage.get_position():.2f} um. Jogging active: {stage._is_jogging}")

    stage.jog(10.0, "backward") # speed = 10um/s, actual_step = 10 * 0.05 = 0.5 um
    print(f"Position after one jog backward: {stage.get_position():.2f} um")
    stage.stop()

    # Test jog when another jog is conceptually active (current implementation allows it, re-sets params)
    # stage.jog(15.0, "forward")
    # print(f"Jogging {stage._jog_direction} at {stage._jog_speed}, Active: {stage._is_jogging}")
    # stage.jog(10.0, "backward")
    # print(f"Jogging {stage._jog_direction} at {stage._jog_speed}, Active: {stage._is_jogging}")
    # stage.stop()

    stage.stop() # Test stopping when not conceptually jogging

    print("\n--- Invalid Jog Parameters ---")
    stage.jog(-5.0, "forward") # speed must be positive
    stage.jog(5.0, "somewhere") # invalid direction

    print("\n--- Stepping while Jogging (conceptual) ---")
    stage.jog(1.0, "forward") # Conceptual jog starts
    print(f"Position: {stage.get_position():.2f}, Jogging: {stage._is_jogging}")
    stage.move_step(1.0, "forward") # This will call stage.stop() first
    print(f"Position: {stage.get_position():.2f}, Jogging: {stage._is_jogging} (should be False)")
    stage.stop() # Ensure fully stopped
