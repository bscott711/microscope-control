# Modular SPIM Control Application

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![GUI Framework](https://img.shields.io/badge/GUI-PySide6-27a9e3)
![Code Style](https://img.shields.io/badge/code%20style-ruff-black)
![License](https://img.shields.io/badge/license-MIT-green)

A Python-based desktop application for controlling a custom Oblique Plane Microscope using an ASI Tiger. It provides a graphical user interface for running complex, automated imaging sequences, including 4D (X, Y, Z, Time) acquisitions with live viewing and calibrated data saving.

---

## ⚠️ Project Status: Under Refactoring ⚠️

This project is currently undergoing a significant architectural refactoring. The goal is to evolve from a single-script prototype into a modular, maintainable, and scalable application built on a professional-grade technical stack. The legacy Tkinter-based code is being phased out in favor of the more robust architecture outlined below.

### ✨ Key Features

* **Live Image Display:** Real-time camera feed displayed in the GUI without freezing.
* **Automated 4D Acquisition:** Configure and run complex sequences with multiple Z-stacks over time.
* **Intelligent Timing Control:** Set time intervals and automatically calculate delays, or run at the maximum possible speed.
* **Real-time Estimates:** The UI provides instant feedback on camera exposure, minimum volume time, and total acquisition duration.
* **Calibrated OME-TIFF Saving:** Optionally save data as multi-page OME-TIFF stacks with correct `ZYX` dimensional metadata and calibrated physical units (`micron`).
* **Graceful Cancellation:** A responsive "Cancel" button allows for the safe and immediate termination of a running acquisition.

### 🗺️ Project Roadmap & Requirements

The detailed plan for the current refactoring, including functional and architectural requirements, is laid out in our official planning document.

➡️ **[View the Project Requirements Document](./docs/REQUIREMENTS.md)**

*(You can place the requirements document we just created in a `docs/` subdirectory and this link will work)*

### 🛠️ Technical Stack

This project is built with modern, high-performance tools:

| Category | Tool | Description |
| :--- | :--- | :--- |
| **GUI Framework** | PySide6 | Official Python bindings for the Qt6 framework. |
| **Microscopy Control** | `pymmcore-plus` | Core library for communicating with Micro-Manager hardware. |
| **Data Handling** | `numpy` | Foundation for all numerical and image array operations. |
| **Image I/O** | `tifffile` | For robustly writing OME-TIFF compliant image stacks. |
| **Package Management** | `uv` | A fast, modern tool for managing Python dependencies. |
| **Code Quality** | `ruff` | For extremely fast code linting and formatting. |
