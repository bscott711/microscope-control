# **🔬 Modular Microscope Control Application**

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![GUI Framework](https://img.shields.io/badge/GUI-PySide6-27a9e3)
![Code Style](https://img.shields.io/badge/code%20style-ruff-black)
![License](https://img.shields.io/badge/license-MIT-green)

A Python-based desktop application for controlling a custom Oblique Plane Microscope (OPM) using an ASI Tiger controller. This project features a robust, modular architecture and a graphical user interface for running hardware-timed imaging sequences with live viewing, real-time scrubbing, and calibrated data saving.

---

![GUI_screenshot.png](https://raw.githubusercontent.com/bscott711/microscope-control/main/GUI_screenshot.png)

## **✨ Key Features**

This application has been refactored to provide a stable and extensible platform for microscope control.

* **Modular Architecture**: Code is cleanly separated into Model, View, Controller, and Hardware layers, making it easy to maintain and extend.  
* **Hardware-Timed Acquisitions**: Executes time-lapse Z-stacks with precise timing managed by the ASI PLogic card.  
* **Live Viewing with Scrubbing**: View incoming frames in real-time and scrub through the data buffer during an active acquisition without interrupting data collection.  
* **Responsive, Thread-Safe Operations**: All long-running acquisitions are performed in a background thread to ensure the GUI remains responsive at all times.  
* **Intelligent Configuration**: The system automatically determines timing parameters based on the user-defined useq acquisition sequence.  
* **Calibrated OME-TIFF Saving**: Optionally save data as multi-page OME-TIFF stacks, now with comprehensive useq sequence metadata and per-frame hardware metadata saved as JSON sidecar files.  
* **Configuration Profiles**: Easily switch between different hardware configurations (e.g., a real system and a demo setup) using simple command-line arguments.  
* **Graceful Cancellation**: A responsive "Cancel" button allows for the safe and immediate termination of a running acquisition.

### **🚀 Getting Started**

#### **Installation**

This project uses uv for fast package management.

1. **Clone the repository:**  
   git clone <https://github.com/bscott711/microscope-control.git>  
   cd microscope-control

2. **Create a virtual environment and install dependencies:**  
   \# Create the virtual environment  
   python \-m venv .venv

   \# Activate the environment (macOS/Linux)  
   source .venv/bin/activate

   \# On Windows, use: .venv\\Scripts\\activate

   \# Install the project in editable mode with uv  
   uv pip install \-e .\[dev\]

#### **Running the Application**

The application is launched using the uscope command-line entry point. You can specify a hardware profile to use.

* **To run with the real hardware:**  
  uscope \--config hardware\_profiles/default\_config.yml

* **To run in Demo Mode (no hardware required):**  
  uscope \--config hardware\_profiles/demo\_config.yml

### **🛠️ Technical Stack**

This project is built with a modern, high-performance Python stack, emphasizing modularity and type safety.

| Category | Tool | Description |
| :---- | :---- | :---- |
| **GUI Framework** | pymmcore-gui | Provides the main window, widgets, and viewer for microscopy. |
| **Core Control** | pymmcore-plus | Core library for communicating with Micro-Manager hardware. |
| **Sequence Control** | useq | For creating expressive, declarative imaging sequences. |
| **Event Handling** | psygnal | A robust, type-safe signal/slot system for event-driven programming. |
| **Data Handling** | numpy | Foundation for all numerical and image array operations. |
| **Image I/O** | tifffile | For robustly writing OME-TIFF compliant image stacks. |
| **Package Mgmt** | uv | A fast, modern tool for managing Python dependencies. |
| **Code Quality** | ruff | For extremely fast code linting and formatting. |
