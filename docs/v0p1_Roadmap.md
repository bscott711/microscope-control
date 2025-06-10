# Refactoring Roadmap: OPM Control Application

This document outlines the phased plan to refactor the OPM control application from a single-script prototype into a modular, maintainable, and robust application using PySide6 and a modern development toolchain.

---

## **Phase 0: Project Setup & Foundation**

**Goal:** Establish a clean, modern project structure and configure the development environment. This creates a solid foundation before any application logic is written.

* [ ] **Initialize Directory Structure:**
  * Create a main project directory.
  * Create a source directory (e.g., `microscope_control/`) to hold the application's Python modules.
  * Create a `docs/` directory for documentation (like the `REQUIREMENTS.md`).
* [ ] **Set Up Virtual Environment:**
  * Use `uv venv` to create a local virtual environment (`.venv`).
* [ ] **Create `pyproject.toml`:**
  * Define project metadata (name, version, author).
  * List all runtime dependencies (`pyside6`, `numpy`, `tifffile`, `pymmcore-plus`, `pillow`).
  * List all development dependencies (`ruff`).
* [ ] **Configure `ruff`:**
  * In `pyproject.toml`, configure `ruff` to enforce the desired code style and linting rules.
* [ ] **Install Dependencies:**
  * Use `uv pip install -e .[dev]` to install the project in editable mode with its development dependencies.
* [ ] **Create `main.py` Entry Point:**
  * Create a main entry point script at the root level that will eventually launch the application.

---

### **Phase 1: Hardware Abstraction Layer (Model)**

**Goal:** Isolate all direct hardware communication into a single, independent class. This class will know *how* to talk to the hardware but won't know anything about acquisition sequences.

* [ ] **Create `HardwareController` Class:**
  * Inside the `microscope_control/` directory, create a new file `hardware.py`.
  * Define a `HardwareController` class that accepts the `mmc` object in its `__init__` method.
* [ ] **Migrate Hardware Functions:**
  * Move all functions that directly call `mmc` or `_execute_tiger_serial_command` into methods of the `HardwareController` class.
  * This includes: `configure_devices_for_slice_scan`, `trigger_slice_scan_acquisition`, `_reset_for_next_volume`, `final_cleanup`, `find_and_set_trigger_mode`, and `getPixelSizeUm`.
* [ ] **Initial Standalone Testing:**
  * Write a simple, temporary script to test the `HardwareController` class directly to ensure hardware commands still work as expected in isolation.

---

### **Phase 2: Acquisition Engine (Controller)**

**Goal:** Create the core logic controller, completely decoupled from the UI. It will manage the state of the acquisition and run in a separate thread.

* [ ] **Create `AcquisitionEngine` Class:**
  * Create a new file `engine.py`.
  * Define an `AcquisitionEngine` class that inherits from `PySide6.QtCore.QObject` to support signals.
* [ ] **Define Signals:**
  * In the `AcquisitionEngine`, define signals for communicating with the GUI:
    * `new_image_ready(image: np.ndarray)`
    * `status_updated(message: str)`
    * `acquisition_finished()`
* [ ] **Implement Worker Method:**
  * Create a primary `run_acquisition()` method. This method will contain the main acquisition loop (the nested `for` loops for time points and Z-slices). **This method will be moved to a `QThread`**.
  * Replace all `root.after()` calls with standard `time.sleep()` for intervals.
  * Replace direct UI updates with signal emissions (e.g., `self.status_updated.emit("...")`).
* [ ] **Implement State Management:**
  * Add methods to `start()`, `stop()`, and `cancel()` the acquisition. These will manage an internal state flag (e.g., `self._is_running`, `self._cancel_requested`) that the `run_acquisition` loop will check.
* [ ] **Integrate `HardwareController`:**
  * The `AcquisitionEngine` will create an instance of the `HardwareController` and call its methods to execute hardware steps.

---

### **Phase 3: Graphical User Interface (View)**

**Goal:** Build the new PySide6 GUI and prepare it to be driven by the `AcquisitionEngine`.

* [ ] **Design UI Layout:**
  * (Optional but recommended) Use Qt Designer to create a `.ui` file that lays out all the widgets visually.
* [ ] **Create `AcquisitionGUI` Class:**
  * Create a new file `gui.py`.
  * Define the main window class `AcquisitionGUI`.
  * Load the `.ui` file (if created) or build the widgets and layouts in code.
* [ ] **Implement UI Slots:**
  * Create methods (slots) in the GUI class to handle updates from the engine's signals:
    * `update_image(image: np.ndarray)`: Converts the NumPy array to a `QPixmap` and displays it.
    * `update_status(message: str)`: Sets the text of the status bar label.
    * `on_acquisition_finished()`: Re-enables the "Run" button and resets the UI state.
* [ ] **Connect User Actions to Engine Control:**
  * Implement methods for button clicks:
    * `_on_run_clicked()`: Gathers all settings from the UI, creates an `AcquisitionEngine` instance, moves it to a `QThread`, connects signals to slots, and starts the thread.
    * `_on_cancel_clicked()`: Calls the `engine.cancel()` method.

---

### **Phase 4: Integration & Finalization**

**Goal:** Connect all the modular components and deliver a fully functional, tested application.

* [ ] **Update `main.py`:**
  * Flesh out the main entry point script to create the `QApplication`, instantiate the `AcquisitionGUI`, and show the main window.
* [ ] **End-to-End Testing:**
  * Perform thorough testing of all features defined in the requirements document.
  * Test the graceful cancellation under various conditions.
  * Verify that saved OME-TIFF files are correct.
* [ ] **Code Cleanup:**
  * Run `ruff format .` and `ruff check --fix .` to ensure the final codebase is clean and consistent.
* [ ] **Update Documentation:**
  * Update the `README.md` with final, correct instructions for setting up and running the refactored application.
