# src/microscope/gui.py
"""
GUI Module

This module contains the main AcquisitionGUI class, which builds and manages
the user interface for the microscope control application using PySide6.
"""

import sys
from typing import Optional

import numpy as np
from pymmcore_plus import CMMCorePlus, find_micromanager
from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QCloseEvent, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .engine import AcquisitionEngine
from .hardware import HardwareController
from .settings import AcquisitionSettings, HardwareConstants


class AcquisitionGUI(QMainWindow):
    """The main window for the microscope control application."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.resize(800, 900)

        # --- Initialize Core Components ---
        # This logic is moved from the TestRunner into the main GUI
        self.mmc = CMMCorePlus.instance()
        self.const = HardwareConstants()
        self._load_hardware_config()

        self.hw_controller = HardwareController(self.mmc, self.const)
        self.engine: Optional[AcquisitionEngine] = None
        self._worker_thread: Optional[QThread] = None

        # --- Build the UI ---
        self._create_widgets()
        self._layout_widgets()
        self._connect_ui_signals()
        self._update_estimates()

    def _load_hardware_config(self):
        """Loads the device adapters and demo configuration."""
        try:
            mm_path = find_micromanager()
            if not mm_path:
                raise RuntimeError("Could not find MM. Run 'mmcore install'.")
            self.mmc.setDeviceAdapterSearchPaths([mm_path])
            self.mmc.loadSystemConfiguration("MMConfig_demo.cfg")
            print("Loaded Demo Hardware Configuration.")
        except Exception as e:
            # In a real app, show a critical error dialog
            print(f"CRITICAL: Failed to load system configuration: {e}")
            sys.exit()

    def _create_widgets(self):
        """Create all the widgets for the user interface."""
        self.ts_group = QGroupBox("Time Series")
        self.time_points_spinbox = QSpinBox(minimum=1, maximum=10000, value=1)
        self.interval_spinbox = QDoubleSpinBox(
            minimum=0, maximum=3600, value=1.0, singleStep=0.1, decimals=1
        )
        self.minimal_interval_checkbox = QCheckBox("Minimal Interval")

        self.vol_group = QGroupBox("Volume & Timing")
        self.slices_spinbox = QSpinBox(minimum=1, maximum=1000, value=10)
        self.step_size_spinbox = QDoubleSpinBox(
            minimum=0.01, maximum=100.0, value=1.0, singleStep=0.1
        )
        self.laser_duration_spinbox = QDoubleSpinBox(
            minimum=1, maximum=1000, value=10.0
        )

        self.save_group = QGroupBox("Data Saving")
        self.save_checkbox = QCheckBox("Save to disk")
        self.save_dir_entry = QLineEdit()
        self.save_dir_entry.setReadOnly(True)
        self.browse_button = QPushButton("Browse...")
        self.prefix_entry = QLineEdit("acquisition")

        self.est_group = QGroupBox("Estimates")
        self.exposure_label = QLabel("...")
        self.min_interval_label = QLabel("...")
        self.total_time_label = QLabel("...")

        self.image_display = QLabel("Camera feed will appear here.")
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_display.setStyleSheet("background-color: black; color: white;")
        self.run_button = QPushButton("Run Acquisition")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setHidden(True)
        self.status_bar = self.statusBar()

    def _layout_widgets(self):
        """Arrange all the created widgets in layouts."""
        main_layout = QVBoxLayout()
        top_controls_layout = QHBoxLayout()
        ts_layout = QFormLayout(self.ts_group)
        ts_layout.addRow("Time Points:", self.time_points_spinbox)
        ts_layout.addRow("Interval (s):", self.interval_spinbox)
        ts_layout.addRow("", self.minimal_interval_checkbox)
        top_controls_layout.addWidget(self.ts_group)

        vol_layout = QFormLayout(self.vol_group)
        vol_layout.addRow("Slices/Volume:", self.slices_spinbox)
        vol_layout.addRow("Step Size (µm):", self.step_size_spinbox)
        vol_layout.addRow("Laser Duration (ms):", self.laser_duration_spinbox)
        top_controls_layout.addWidget(self.vol_group)
        main_layout.addLayout(top_controls_layout)

        save_layout = QGridLayout(self.save_group)
        save_layout.addWidget(self.save_checkbox, 0, 0)
        save_layout.addWidget(self.save_dir_entry, 0, 1)
        save_layout.addWidget(self.browse_button, 0, 2)
        save_layout.addWidget(QLabel("File Prefix:"), 0, 3)
        save_layout.addWidget(self.prefix_entry, 0, 4)
        main_layout.addWidget(self.save_group)

        est_layout = QFormLayout(self.est_group)
        est_layout.addRow("Camera Exposure (ms):", self.exposure_label)
        est_layout.addRow("Min. Interval/Volume (s):", self.min_interval_label)
        est_layout.addRow("Estimated Total Time:", self.total_time_label)
        main_layout.addWidget(self.est_group)

        main_layout.addWidget(self.image_display, stretch=1)

        bottom_button_layout = QHBoxLayout()
        bottom_button_layout.addWidget(self.run_button)
        bottom_button_layout.addWidget(self.cancel_button)
        bottom_button_layout.addStretch()
        main_layout.addLayout(bottom_button_layout)

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def _connect_ui_signals(self):
        """Connect widget signals to handler methods (slots)."""
        self.browse_button.clicked.connect(self._on_browse)
        self.run_button.clicked.connect(self._on_run)
        self.cancel_button.clicked.connect(self._on_cancel)
        self.minimal_interval_checkbox.toggled.connect(
            self.interval_spinbox.setDisabled
        )

        for widget in (
            self.time_points_spinbox,
            self.interval_spinbox,
            self.slices_spinbox,
            self.laser_duration_spinbox,
        ):
            widget.valueChanged.connect(self._update_estimates)
        self.minimal_interval_checkbox.stateChanged.connect(self._update_estimates)

    def _on_run(self):
        """Called when the 'Run' button is clicked. Sets up and starts the engine."""
        settings = self._get_settings_from_gui()
        self.engine = AcquisitionEngine(self.hw_controller, settings)
        self._worker_thread = QThread()
        self.engine.moveToThread(self._worker_thread)

        # Connect engine signals to GUI slots
        self._worker_thread.started.connect(self.engine.run_acquisition)
        self.engine.acquisition_finished.connect(self.on_acquisition_finished)
        self.engine.new_image_ready.connect(self.update_image)
        self.engine.status_updated.connect(self.update_status)

        self.run_button.setHidden(True)
        self.cancel_button.setHidden(False)
        self._worker_thread.start()

    @Slot()
    def _on_cancel(self):
        """Called when 'Cancel' is clicked. Requests the engine to stop."""
        if self.engine:
            self.engine.cancel()
        self.cancel_button.setEnabled(False)
        self.update_status("Cancelling...")

    @Slot(str)
    def _on_browse(self):
        """Opens a dialog to select a save directory."""
        directory = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if directory:
            self.save_dir_entry.setText(directory)

    @Slot()
    def _update_estimates(self):
        """Calculates and updates the timing estimates in the GUI."""
        settings = self._get_settings_from_gui()
        self.exposure_label.setText(f"{settings.camera_exposure_ms:.2f}")

        overhead_factor = 1.10
        total_exposure_ms = settings.num_slices * settings.camera_exposure_ms
        min_interval_s = (total_exposure_ms * overhead_factor) / 1000.0
        self.min_interval_label.setText(f"{min_interval_s:.2f}")

        if settings.is_minimal_interval:
            time_per_volume = min_interval_s
        else:
            time_per_volume = max(settings.time_interval_s, min_interval_s)

        total_seconds = time_per_volume * settings.time_points
        h = int(total_seconds // 3600)
        m = int((total_seconds % 3600) // 60)
        s = int(total_seconds % 60)
        self.total_time_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _get_settings_from_gui(self) -> AcquisitionSettings:
        """Creates an AcquisitionSettings object from the current GUI values."""
        return AcquisitionSettings(
            num_slices=self.slices_spinbox.value(),
            step_size_um=self.step_size_spinbox.value(),
            laser_trig_duration_ms=self.laser_duration_spinbox.value(),
            time_points=self.time_points_spinbox.value(),
            time_interval_s=self.interval_spinbox.value(),
            is_minimal_interval=self.minimal_interval_checkbox.isChecked(),
            should_save=self.save_checkbox.isChecked(),
            save_dir=self.save_dir_entry.text(),
            save_prefix=self.prefix_entry.text(),
        )

    @Slot(np.ndarray)
    def update_image(self, image: np.ndarray):
        """Converts a numpy array from the engine to a QPixmap and displays it."""
        h, w = image.shape
        q_image = QImage(image.data, w, h, w, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image)
        self.image_display.setPixmap(
            pixmap.scaled(
                self.image_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    @Slot(str)
    def update_status(self, message: str):
        """Updates the status bar with a message from the engine."""
        self.status_bar.showMessage(message)

    @Slot()
    def on_acquisition_finished(self):
        """Resets the GUI to its idle state after an acquisition finishes."""
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
        self.run_button.setHidden(False)
        self.cancel_button.setHidden(True)
        self.cancel_button.setEnabled(True)
        self.status_bar.showMessage("Ready")

    def closeEvent(self, event: QCloseEvent):
        """Ensures the engine is stopped cleanly when the window is closed."""
        if self.engine and self.engine._is_running:
            self._on_cancel()
            self.on_acquisition_finished()
        event.accept()
