# **Modular OPM Control Application**

A Python-based desktop application for controlling a custom Oblique Plane Microscope (OPM) using an ASI Tiger controller. This project provides a graphical user interface for running automated imaging sequences with live viewing and calibrated data saving.

## **✨ Key Features**

This application provides a solid foundation for OPM control with the following features implemented:

* **Live Image Display:** A real-time camera feed displayed in the GUI.  
* **Snap Image:** Acquire a single frame with the current settings.  
* **Automated Time-Lapse Z-Stack:** Configure and run sequences with multiple Z-stacks over time.  
* **Intelligent Timing Control:** Set time intervals between volumes or run at the maximum possible speed.  
* **Real-time Estimates:** The UI provides instant feedback on camera exposure, minimum volume time, and total acquisition duration.  
* **Calibrated OME-TIFF Saving:** Optionally save data as multi-page OME-TIFF stacks with ZYX dimensional metadata.  
* **Graceful Cancellation:** A responsive "Cancel" button allows for the safe and immediate termination of a running acquisition.  
* **Demo Mode:** Run the application without any physical hardware for testing and development.

## **🚀 Getting Started**

### **Installation**

This project uses uv for fast package management.

1. **Clone the repository:**  
   git clone <https://github.com/bscott711/microscope-control.git>  
   cd microscope-control

2. **Create a virtual environment and install dependencies:**  
   \# Create the virtual environment  
   python \-m venv .venv  
   source .venv/bin/activate  \# On Windows, use \`.venv\\Scripts\\activate\`

   \# Install the project in editable mode with uv  
   uv pip install \-e .\[dev\]

### **Running the Application**

* With real hardware:  
  Make sure your hardware configuration file is correctly specified in src/microscope/core/constants.py. Then, run:  
  microscope-control

* In Demo Mode (no hardware required):  
  Use the MICROSCOPE\_DEMO environment variable.  
  **On macOS/Linux:**  
  arch \-x86\_64 zsh  
  source .venv/bin/activate
  MICROSCOPE\_DEMO=1 microscope-control

  **On Windows (PowerShell):**  
  $env:MICROSCOPE\_DEMO="1"  
  microscope-control

## **🏛️ Architecture**

This application follows a Model-View-Controller (MVC) inspired architecture to ensure a clear separation of concerns.  
src/microscope/  
├── controller/  \# (Controller) Orchestrates the application  
├── core/        \# (Model) Handles data, hardware, and acquisition logic  
│   ├── engine/  
│   └── hardware/  
└── main.py      \# Main application entry point

* **Controller (controller/)**: The "brain" of the application. It listens for user actions from the View (the GUI) and tells the Model what to do. It's broken down into sub-controllers for specific actions (actions.py, mda.py).  
* **Model (core/)**: Represents the application's data and business logic.  
  * **hardware/**: A component-based package where each module is responsible for a single piece of hardware (e.g., camera.py, galvo.py, plogic.py).  
  * **engine/**: Manages the state and execution of complex acquisition sequences. It uses a worker.py to run hardware-timed loops in a separate thread, ensuring the GUI remains responsive.  
  * **datastore.py**: Handles saving data to disk, including metadata.  
* **View**: The user interface is provided by pymmcore-gui. The application logic does not directly interact with UI widgets; instead, the controller connects GUI signals to its methods.

## **🛠️ Technical Stack**

This project is built with a modern, high-performance Python stack:

| Category | Tool | Description |
| :---- | :---- | :---- |
| **GUI Framework** | PySide6 | Official Python bindings for the Qt6 framework. |
| **GUI Generation** | pymmcore-gui | Pre-built Qt widgets for microscopy applications. |
| **Microscopy Control** | pymmcore-plus | Core library for communicating with Micro-Manager hardware. |
| **Data Handling** | numpy | Foundation for all numerical and image array operations. |
| **Image I/O** | tifffile | For robustly writing OME-TIFF compliant image stacks. |
| **Package Management** | uv | A fast, modern tool for managing Python dependencies. |
| **Code Quality** | ruff | For extremely fast code linting and formatting. |
