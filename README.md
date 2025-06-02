# OPM Microscope Control System 🔬

**A modern microscopy control framework designed for Oblique Plane Microscopy (OPM), built with `uv`, `pymmcore-plus`, and `napari`. This system provides comprehensive, user-friendly control over various hardware components for advanced imaging applications.**

---

## 🌟 Key Features

This control system offers a range of powerful features for OPM imaging:

* **Virtual Z-Stacks via Galvo Mirror**:
  * Enables rapid and precise axial scanning by controlling a galvanometric mirror.
  * Allows for fast volumetric imaging without mechanical Z-stage movement, minimizing vibrations and sample drift.
* **Dual CRISP Focus Control (O1/O3)**:
  * Provides independent and coordinated autofocus control for two objectives (e.g., illumination O1 and detection O3 objectives in an OPM setup).
  * Ensures consistently sharp images across different fields of view and during long-term experiments.
* **Multi-Camera Synchronization**:
  * Supports precise triggering and synchronization of multiple cameras.
  * Ideal for simultaneous multi-channel fluorescence imaging, multi-view (e.g., SPIM) configurations, or other applications requiring coordinated camera capture.
* **Laser Combination Control**:
  * Offers flexible management and rapid switching of multiple laser lines.
  * Allows for complex illumination sequences and multi-color fluorescence excitation.
* **Automated Calibration Routines**:
  * **CRISP Calibration**: Streamlined, guided procedures for calibrating the Continuous Reflective Interface Sample Placement (CRISP) autofocus system for optimal performance.
  * **Galvo Calibration**: Routines to calibrate the galvo mirror for accurate Z-stack positioning, field of view alignment, and scan linearity.
* **Modular and Extensible Architecture**:
  * Built upon `pymmcore-plus` for broad hardware compatibility with a vast range of microscopy devices supported by Micro-Manager.
  * Leverages `napari` for an intuitive, interactive, and multi-dimensional image viewing experience, as well as a platform for custom plugin development.
* **Modern Python Tooling**:
  * Utilizes `uv` for fast, reliable, and easy-to-manage project dependencies and virtual environments.

---

## 🏗️ System Architecture

The OPM Microscope Control System is built upon a robust and flexible software stack:

* **`pymmcore-plus`**: This library acts as the core hardware abstraction layer. It provides Pythonic control over microscope hardware by interfacing with Micro-Manager device adapters. This allows the system to communicate with and control a wide array of cameras, stages, lasers, shutters, and other peripherals.
* **`napari`**: A fast, interactive, multi-dimensional image viewer for Python. In this system, `napari` serves as the primary graphical user interface (GUI). It provides real-time image display, tools for data interaction, and a plugin architecture that can be extended with custom widgets for controlling specific aspects of the OPM system.
* **`uv`**: A modern and extremely fast Python package installer and resolver. It is used to manage project dependencies and create isolated virtual environments, ensuring reproducibility and simplifying the setup process.

These components work together to provide a cohesive environment for instrument control, data acquisition, and visualization, tailored for the specific needs of OPM.

---

## 🛠️ Setup & Installation

Follow these steps to get the OPM Microscope Control System up and running.

### Prerequisites

* **Python**: Version 3.9 or higher is recommended.
* **`uv`**: The `uv` Python packaging tool. If you don't have it installed, you can typically install it via pip:

    ```bash
    pip install uv
    ```

* **Hardware Drivers**: Ensure that all necessary drivers for your specific microscope hardware (cameras, galvo controllers, DAQ cards, CRISP units, lasers, etc.) are installed and functioning correctly on your operating system. Refer to the documentation provided by your hardware manufacturers.
* **Git**: (Optional, but recommended for cloning the repository if it's hosted on a platform like GitHub).

### Installation Steps

1. **Clone the Repository (if applicable)**:
    If the project code is hosted in a Git repository, clone it to your local machine:

    ```bash
    git clone <your-repository-url>
    cd opm-microscope-control-system # Or your project's root directory name
    ```

2. **Create Virtual Environment and Install Dependencies**:
    This project uses `uv` for dependency management. The following command will create a virtual environment (typically named `.venv` in the project root) and install all required packages, including development dependencies:

    ```bash
    uv install -e dev
    ```

    * The `-e` flag installs the project in "editable" mode, which is useful for development.
    * The `dev` argument assumes you have an optional dependency group named `[project.optional-dependencies.dev]` in your `pyproject.toml` file for development tools (e.g., linters, testing frameworks).

    If you only want to install runtime dependencies (e.g., for deployment rather than development):

    ```bash
    uv install
    ```

3. **Hardware Configuration File**:
    * `pymmcore-plus` (and Micro-Manager) requires a hardware configuration file (usually with a `.cfg` extension) that defines all the hardware components in your microscope system.
    * You will need to create or adapt a Micro-Manager configuration file for your specific OPM setup.
    * Place this configuration file in an accessible location (e.g., a `config/` directory within the project or a user-defined path). The application will need to be pointed to this file, either through a settings dialog or a configuration script.

---

## 🚀 Usage

Once the installation is complete, you can run the control system.

1. **Activate the Virtual Environment**:
    If you are not already in the virtual environment created by `uv`, activate it:

    ```bash
    # On Linux/macOS
    source .venv/bin/activate

    # On Windows (Command Prompt)
    # .venv\Scripts\activate.bat

    # On Windows (PowerShell)
    # .venv\Scripts\Activate.ps1
    ```

2. **Launch the Application**:
    The exact command to launch the application will depend on how your project's entry points are defined (e.g., in `pyproject.toml` under `[project.scripts]`). It might be something like:

    ```bash
    python -m opm_control.main_gui # Example: if your main GUI is in main_gui.py within an opm_control package
    ```

    Or, if you have a console script defined:

    ```bash
    opm-control # Example script name
    ```

    Refer to your project's specific documentation or `pyproject.toml` for the correct launch command.

3. **Connect to Hardware**:
    Within the application, there should be an option to load your Micro-Manager hardware configuration (`.cfg`) file. This will initialize communication with all connected devices.

4. **Perform Calibrations**:
    * Before starting experiments, it is crucial to run the available calibration routines, especially for CRISP and the galvo mirror.
    * Navigate to the "Calibration" section or relevant controls within the GUI.
    * Follow the on-screen instructions or documented procedures for each calibration task.

5. **Configure Imaging Parameters**:
    * Set parameters such as exposure times, laser power/wavelengths, Z-stack range and step size, camera acquisition modes, etc.

6. **Acquire Data**:
    * Use the acquisition controls (e.g., "Start Acquisition," "Snap Image") provided in the `napari` interface or custom control panels.
    * Live images and acquired data should be displayed within the `napari` viewer.

---

## ⚙️ Configuration

* **Micro-Manager Hardware Configuration (`.cfg` file)**: This is the primary configuration file defining your microscope hardware. It's essential for `pymmcore-plus` to function.
* **Application Settings**: The application might have its own settings file (e.g., `config.yaml`, `settings.ini`, or stored via `napari` preferences) for user preferences, default paths, calibration parameters, etc. Details on these settings should be found within the application or its specific documentation.

---

## 🔩 Hardware Compatibility & Requirements

This control system is designed to be flexible, but a typical OPM setup would involve:

* **Microscope Body/Optomechanics**: Custom or commercial framework for OPM.
* **Cameras**: Scientific CMOS (sCMOS) or EMCCD cameras compatible with Micro-Manager (e.g., from Hamamatsu, Andor, Photometrics, PCO).
* **Galvanometric Mirror System**: For creating the virtual Z-scan (light sheet tilting). (e.g., from Thorlabs, Cambridge Technology, SCANLAB).
* **Objective Lenses**: Appropriate high-NA objectives for illumination and detection paths.
* **CRISP Autofocus System**: Or a similar continuous hardware autofocus mechanism.
* **Lasers & Laser Combiner**: A suite of lasers for desired excitation wavelengths, potentially managed by a laser combiner (e.g., from Coherent, Omicron, Vortran, Toptica).
* **Data Acquisition (DAQ) Card**: Often used for precise synchronization of hardware components like galvos, cameras, and lasers (e.g., National Instruments).
* **Motorized Stages**: For sample positioning (XYZ), objective focusing (if not solely reliant on galvo/CRISP).
* **Computer**: A reasonably powerful computer with sufficient RAM, CPU cores, and fast storage (SSD recommended). Ensure appropriate interface cards (e.g., PCIe for DAQ, CameraLink if used) are installed.

---

## 🗺️ Roadmap / Future Enhancements

This section can outline planned features or areas for future development:

* [ ] Integration of advanced image processing pipelines (e.g., deconvolution, registration) accessible via `napari` plugins.
* [ ] Support for adaptive optics (AO) components and calibration.
* [ ] Development of more sophisticated multi-dimensional acquisition sequences (e.g., time-lapse with event-triggered changes).
* [ ] Enhanced real-time data analysis and feedback loops.
* [ ] Expanded library of pre-defined calibration routines.
* [ ] User management and experiment logging features.
* [ ] Cloud integration for data storage and remote monitoring (optional).

---

## 🤝 Contributing

We welcome contributions to the OPM Microscope Control System! If you're interested in contributing, please:

1. **Fork the repository.**
2. **Create a new branch** for your feature or bug fix (e.g., `git checkout -b feature/my-new-feature` or `bugfix/issue-tracker-id`).
3. **Make your changes.** Adhere to the project's coding style (e.g., run linters like Ruff, formatters like Black).
4. **Write tests** for any new functionality or bug fixes.
5. **Ensure all tests pass.**
6. **Commit your changes** with clear and descriptive commit messages.
7. **Push your branch** to your forked repository.
8. **Open a Pull Request** against the `main` (or `develop`) branch of the original repository. Please provide a detailed description of your changes in the PR.

---
