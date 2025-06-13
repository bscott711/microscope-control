# Refactoring Plan 3.0: Full MVC-Inspired Architecture

This plan formalizes the separation of the data and hardware state (Model), the user interface (View), and the application logic that coordinates them (Controller).

Phase 1: New Application-Wide Directory Structure
We will restructure the src/microscope/ directory to reflect the MVC pattern. This creates clear, logical boundaries for each part of the application.

src/
└── microscope/
    ├── __init__.py               # Main package indicator
    ├── __main__.py               # Application entry point
    |
    ├── core/                     # CONTROLLER (Application Logic)
    │   ├── __init__.py
    │   └── acquisition.py        # The high-level acquisition sequencer
    |
    ├── hardware/                 # MODEL (Hardware Abstraction Layer)
    │   ├── __init__.py
    │   ├── hal.py                # Main HAL class (facade pattern)
    │   ├── camera.py             # Camera-specific controls
    │   ├── galvo.py              # Galvo-specific controls
    │   ├── plogic.py             # PLogic programming logic
    │   └── stage.py              # Stage-specific controls
    |
    └── ui/                       # VIEW (User Interface)
        ├── __init__.py
        ├── main_window.py        # The main QMainWindow (the container)
        |
        ├── widgets/              # Reusable, single-purpose UI components
        │   ├── __init__.py
        │   ├── camera_view.py    # The image display QLabel
        │   ├── controls.py       # The magicgui acquisition settings panel
        │   ├── main_panel.py     # The main action buttons (Run, Snap, etc.)
        │   └── status.py         # The estimates and status bar widgets
        |
        └── styles/               # UI Styling
            └── __init__.py
            └── style.qss         # A dedicated Qt Stylesheet

Phase 2: Deconstruct the GUI (The View)
The current monolithic AcquisitionGUI class will be broken down into smaller, single-purpose widgets. This makes the UI modular and easier to manage.

Create UI Component Widgets (ui/widgets/):

controls.py: Will contain the magicgui widget for acquisition parameters. It will emit a signal whenever a value changes.
camera_view.py: Will contain the QLabel for displaying images. It will have a public slot to update the pixmap.
status.py: Will contain the QFormLayout for displaying estimated times and have slots to update the text labels.
main_panel.py: Will contain the Run, Snap, Live, and Cancel buttons. It will emit signals like run_clicked, snap_clicked, etc.
Create the Main Window (ui/main_window.py):

The AcquisitionGUI class will now be a simple container. Its job is to instantiate the various widgets from the ui/widgets/ directory and arrange them in a layout. It will contain almost no application logic.
Implement Styling (ui/styles/):

A style.qss file will be created. This file will contain CSS-like rules for styling all the Qt widgets (e.g., button colors, font sizes, spacing).
The main_window will load this stylesheet and apply it to the entire application, ensuring a consistent and professional look.
Phase 3: Implement the Component-Based HAL (The Model)
This phase remains the same as our previous plan, as it is already aligned with a component-based approach.

Device-Specific Controllers (hardware/ sub-files): Create CameraController, GalvoController, PLogicController, and StageController classes, each responsible for a single piece of hardware.
HAL Facade (hardware/hal.py): The HardwareAbstractionLayer class will compose these controllers. It will provide the simple public API (setup_for_acquisition, start_acquisition, etc.) that delegates calls to its internal controller instances.
Phase 4: Implement the Core Application Logic (The Controller)
This is the most significant change. We will remove all complex logic and state management from the GUI and place it in the controller.

Acquisition Sequencer (core/acquisition.py):

The logic from the old AcquisitionWorker (the for loop for time points, image processing loop, etc.) will reside in a new AcquisitionSequencer class. This class will be a QObject designed to be moved to a QThread.
The Main Controller (__main__.py will be simplified, and a new core/application.py could be introduced):

A central ApplicationController class will be created. This is the "brain" of the application.
Initialization: It will instantiate the HardwareAbstractionLayer and the AcquisitionGUI.
Signal Connection: This is the critical step. The controller will connect the signals from the View to the slots in the Model and the Sequencer.
gui.main_panel.run_clicked.connect(self.sequencer.start)
gui.main_panel.snap_clicked.connect(self.hal.snap)
self.sequencer.new_image.connect(gui.camera_view.set_image)
self.sequencer.status_update.connect(gui.status_panel.set_status_text)
This completely decouples the ui from the hardware and core logic. The GUI only knows that a button was clicked; the controller decides what that click means.
