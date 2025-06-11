# Roadmap: v0.3.0 - Live Scan & Navigation

Branch Goal: To add live imaging and comprehensive navigation controls to the application, allowing users to find a region of interest before starting a 4D acquisition. This includes support for continuous jogging and remappable external input devices like joysticks and wheels.

Phase 0: Foundation & Configuration

Goal: Update the project configuration to include the new hardware devices needed for navigation.

[ ] Update Project Version: In pyproject.toml, increment the version to 0.3.0.dev0.

[ ] Add Navigation Device Labels: In settings.py, add new entries to HardwareConstants for all navigation devices, such as the XY stage, any additional Z stages or piezos, and the ASI input devices (e.g., JOYSTICK_LABEL, WHEEL_LABEL).

[ ] Update Demo Configuration: In __main__.py, update the demo device loading sequence to include dummy XY and Z stages (e.g., DemoCamera/DXYStage, DemoCamera/DStage) to facilitate UI development and testing without real hardware.

Phase 1: Hardware Controller Expansion

Goal: Extend the HardwareController to provide a complete API for stage movement, live imaging, and input device management.

[ ] Implement Generic Position Methods:

Create a get_position(device_label: str) -> float method.

Create a set_position(device_label: str, position: float) method that moves a stage and waits for it to finish.

Create a set_relative_position(device_label: str, offset: float) method.

[ ] Implement Jogging Methods:

Create a start_jog(device_label: str, speed_microns_per_sec: float) method.

Create a stop_jog(device_label: str) method that halts jogging for a specific device.

Implement a master stop_all_stages() method.

[ ] Implement Input Device Mapping Methods:

Create a get_joystick_assignments() -> dict method to query the Tiger controller for current joystick axis mappings.

Create a set_joystick_assignment(axis: str, device: str) method to assign a joystick axis (e.g., "X", "Y") to control a specific hardware device axis.

Implement similar get_wheel_assignment() and set_wheel_assignment() methods.

[ ] Implement Live Scan Methods:

Add start_live_scan(exposure_ms: float) to put the camera into a continuous acquisition mode.

Add stop_live_scan() to stop the continuous acquisition.

[ ] Create Position Polling Method:

Add a get_all_positions() -> dict method that queries all registered navigation devices and returns a dictionary of their current positions.

Phase 2: GUI - Navigation & Input Control

Goal: Design and build new, reusable UI components for navigation and input device configuration.

[ ] Create navigation_panel.py:

Design the Widget: The NavigationPanel will contain:

A grid of read-only displays for X, Y, Z, Piezo, and Galvo positions.

QDoubleSpinBox widgets for entering "go-to" positions.

QPushButton widgets for relative moves (+ and -) and jogging (◀ and ▶). Jog buttons will emit signals on pressed and released.

A "Go To" button for each axis.

A master "STOP" button that halts all movement.

Define Signals: Emit signals like move_requested, jog_started, and jog_stopped.

[ ] Create input_mapping_panel.py:

Design the Widget: Create a new self-contained panel for remapping hardware.

It will feature QComboBox widgets for each input axis (e.g., "Joystick X", "Joystick Y", "Filter Wheel").

The combo boxes will be populated with a list of available controllable hardware axes.

Define Signals: Emit a mapping_changed(input_device: str, new_hardware_axis: str) signal whenever a user selects a new mapping.

Phase 3: Navigation & Live Engine

Goal: Create a new, dedicated engine to handle the continuous, low-latency tasks of position polling, live imaging, and responding to navigation commands.

[ ] Create LiveEngine Class:

In a new file live_engine.py, create a LiveEngine class that inherits from QObject.

[ ] Implement Position Polling Loop:

Create a worker method (_run_position_updater) that runs in a loop in a QThread, calling hardware.get_all_positions() and emitting a positions_updated(positions: dict) signal.

[ ] Implement Live Scan Loop:

Create a worker method (_run_live_scan) that starts the camera's live mode and emits new_live_image(image: np.ndarray) signals.

[ ] Implement Public Control Slots:

Create public slots to be called from the main GUI thread:

start_polling(), stop_polling()

start_live_view(), stop_live_view()

move_stage(axis: str, position: float)

jog_stage(axis: str, speed: float)

stop_stage(axis: str)

update_input_mapping(input_device: str, hardware_axis: str)

Phase 4: Integration into Main GUI

Goal: Integrate the new navigation and input control panels into the main application window.

[ ] Add Navigation & Mapping Panels to AcquisitionGUI: Instantiate the new panels and add them to a collapsible section of the main window.

[ ] Integrate LiveEngine:

The AcquisitionGUI will create and manage an instance of the LiveEngine in a separate thread.

Connect the GUI's "Live" button and the navigation panels' signals to the appropriate LiveEngine slots.

[ ] Connect Signals and Slots:

Connect the LiveEngine's positions_updated signal back to the NavigationPanel's display slots.

Connect the LiveEngine's new_live_image signal to the AcquisitionGUI's main image display slot.

[ ] Final Testing:

Thoroughly test all navigation controls (absolute, relative, jog), live view, and input device mapping. Ensure these new features do not interfere with the main 4D acquisition sequence.
