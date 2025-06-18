# Modular OPM Control Application

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![GUI Framework](https://img.shields.io/badge/GUI-PySide6-27a9e3)
![Code Style](https://img.shields.io/badge/code%20style-ruff-black)
![License](https://img.shields.io/badge/license-MIT-green)

A Python-based desktop application for controlling a custom Oblique Plane Microscope (OPM) using an ASI Tiger controller. This project provides a graphical user interface for running automated imaging sequences with live viewing and calibrated data saving.

---

![GUI_screenshot.png](https://raw.githubusercontent.com/bscott711/microscope-control/main/GUI_screenshot.png)

## ✨ Key Features

This application provides a solid foundation for OPM control with the following features implemented:

* **Live Image Display:** A real-time camera feed displayed in the GUI.
* **Snap Image:** Acquire a single frame with the current settings.
* **Automated Time-Lapse Z-Stack:** Configure and run sequences with multiple Z-stacks over time.
* **Intelligent Timing Control:** Set time intervals between volumes or run at the maximum possible speed.
* **Real-time Estimates:** The UI provides instant feedback on camera exposure, minimum volume time, and total acquisition duration.
* **Calibrated OME-TIFF Saving:** Optionally save data as multi-page OME-TIFF stacks with `ZYX` dimensional metadata.
* **Graceful Cancellation:** A responsive "Cancel" button allows for the safe and immediate termination of a running acquisition.
* **Demo Mode:** Run the application without any physical hardware for testing and development.

## 🚀 Getting Started

### Installation

This project uses `uv` for fast package management.

1. **Clone the repository:**

    ```bash
    git clone [https://github.com/bscott711/microscope-control.git](https://github.com/bscott711/microscope-control.git)
    cd microscope-control
    ```

2. **Create a virtual environment and install dependencies:**

    ```bash
    # Create the virtual environment
    python -m venv .venv
    source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`

    # Install the project in editable mode with uv
    uv pip install -e .[dev]
    ```

### Running the Application

* **With real hardware:**
    Make sure your hardware configuration file is correctly specified in `src/microscope/config.py`. Then, run:

    ```bash
    microscope-control
    ```

* **In Demo Mode (no hardware required):**
    Use the `MICROSCOPE_DEMO` environment variable.

    **On macOS/Linux:**

    ```bash
    arch -x86_64 zsh
    source .venv/bin/activate  
    MICROSCOPE_DEMO=1 microscope-control
    ```

    **On Windows (PowerShell):**

    ```powershell
    $env:MICROSCOPE_DEMO="1"
    microscope-control
    ```

## 🛠️ Technical Stack

This project is built with a modern, high-performance Python stack:

| Category             | Tool                 | Description                                                  |
| :------------------- | :------------------- | :----------------------------------------------------------- |
| **GUI Framework** | `PySide6`              | Official Python bindings for the Qt6 framework.              |
| **GUI Generation** | `magicgui`           | For rapidly creating Qt widgets from Python functions.       |
| **Microscopy Control** | `pymmcore-plus`      | Core library for communicating with Micro-Manager hardware.  |
| **Data Handling** | `numpy`              | Foundation for all numerical and image array operations.     |
| **Image I/O** | `tifffile`           | For robustly writing OME-TIFF compliant image stacks.        |
| **Package Management** | `uv`                 | A fast, modern tool for managing Python dependencies.        |
| **Code Quality** | `ruff`               | For extremely fast code linting and formatting.              |
