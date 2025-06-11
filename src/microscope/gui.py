# src/microscope/gui.py
"""
GUI Module

This module contains the main AcquisitionGUI class, which builds and manages
the user interface for the microscope control application using PySide6.
"""

import os
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
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .engine import AcquisitionEngine
from .hardware import HardwareController
from .live_engine import LiveEngine
from .navigation_panel import NavigationPanel
from .settings import AcquisitionSettings, HardwareConstants


class AcquisitionGUI(QMainWindow):
    """The main window for the microscope control application."""

    # --- Type Hint Declarations for Instance Attributes ---
    # Core Components
    mmc: CMMCorePlus
    const: HardwareConstants
    hw_controller: HardwareController
    acq_engine: Optional[AcquisitionEngine]
    _acq_thread: Optional[QThread]
    live_engine: Optional[LiveEngine]
    _live_thread: Optional[QThread]

    # UI Widgets
    nav_panel: NavigationPanel
    live_button: QPushButton
    live_exposure_spinbox: QDoubleSpinBox
    ts_group: QGroupBox
    time_points_spinbox: QSpinBox
    interval_spinbox: QDoubleSpinBox
    minimal_interval_checkbox: QCheckBox
    vol_group: QGroupBox
    slices_spinbox: QSpinBox
    step_size_spinbox: QDoubleSpinBox
    laser_duration_spinbox: QDoubleSpinBox
    save_group: QGroupBox
    save_checkbox: QCheckBox
    save_dir_entry: QLineEdit
    browse_button: QPushButton
    prefix_entry: QLineEdit
    est_group: QGroupBox
    exposure_label: QLabel
    min_interval_label: QLabel
    total_time_label: QLabel
    image_display: QLabel
    run_button: QPushButton
    cancel_button: QPushButton
    status_bar: QStatusBar
    # --- End of Declarations ---

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.resize(800, 900)

        # --- Initialize Core Components ---
        self.mmc = CMMCorePlus.instance()
        self.const = HardwareConstants()
        self._load_hardware_config()

        self.hw_controller = HardwareController(self.mmc, self.const)
        self.acq_engine = None
        self._acq_thread = None
        self.live_engine = None
        self._live_thread = None

        # --- Build the UI ---
        self._create_widgets()
        self._layout_widgets()
        self._connect_ui_signals()
        self._update_estimates()
        self._start_live_engine()

    def _load_hardware_config(self):
        """Loads the device adapters and the system configuration file."""
        try:
            mm_path = find_micromanager()
            if not mm_path:
                raise RuntimeError("Could not find MM. Run 'mmcore install'.")
            self.mmc.setDeviceAdapterSearchPaths([mm_path])

            config_path = os.path.abspath(self.const.CFG_PATH)
            if not os.path.exists(config_path):
                raise FileNotFoundError(
                    f"Hardware config file not found at: {config_path}",
                )

            print(f"Loading hardware configuration: {config_path}")
            self.mmc.loadSystemConfiguration(config_path)
            print("Hardware configuration loaded successfully.")

        except Exception as e:
            print(f"CRITICAL: Failed to load system configuration: {e}")
            sys.exit()

    def _create_widgets(self):
        """Create all the widgets for the user interface."""
        self.nav_panel = NavigationPanel()
        self.live_button = QPushButton("Live")
        self.live_button.setCheckable(True)
        self.live_exposure_spinbox = QDoubleSpinBox(
            minimum=1,
            maximum=1000,
            value=30.0,
        )

        self.ts_group = QGroupBox("Time Series Acquisition")
        self.time_points_spinbox = QSpinBox(minimum=1, maximum=10000, value=1)
        self.interval_spinbox = QDoubleSpinBox(
            minimum=0,
            maximum=3600,
            value=1.0,
            singleStep=0.1,
            decimals=1,
        )
        self.minimal_interval_checkbox = QCheckBox("Minimal Interval")

        self.vol_group = QGroupBox("Volume & Timing")
        self.slices_spinbox = QSpinBox(minimum=1, maximum=1000, value=10)
        self.step_size_spinbox = QDoubleSpinBox(
            minimum=0.01,
            maximum=100.0,
            value=1.0,
            singleStep=0.1,
        )
        self.laser_duration_spinbox = QDoubleSpinBox(
            minimum=1,
            maximum=1000,
            value=10.0,
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
        self.status_bar.showMessage("Ready")

    def _layout_widgets(self):
        """Arrange all the created widgets in layouts."""
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.nav_panel)

        live_layout = QHBoxLayout()
        live_layout.addWidget(self.live_button)
        live_layout.addWidget(QLabel("Exposure (ms):"))
        live_layout.addWidget(self.live_exposure_spinbox)
        live_layout.addStretch()
        main_layout.addLayout(live_layout)

        acq_controls_layout = QHBoxLayout()
        ts_layout = QFormLayout(self.ts_group)
        ts_layout.addRow("Time Points:", self.time_points_spinbox)
        ts_layout.addRow("Interval (s):", self.interval_spinbox)
        ts_layout.addRow("", self.minimal_interval_checkbox)
        acq_controls_layout.addWidget(self.ts_group)

        vol_layout = QFormLayout(self.vol_group)
        vol_layout.addRow("Slices/Volume:", self.slices_spinbox)
        vol_layout.addRow("Step Size (µm):", self.step_size_spinbox)
        vol_layout.addRow("Laser Duration (ms):", self.laser_duration_spinbox)
        acq_controls_layout.addWidget(self.vol_group)
        main_layout.addLayout(acq_controls_layout)

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
            self.interval_spinbox.setDisabled,
        )
        self.live_button.toggled.connect(self._on_live_toggled)

        for widget in (
            self.time_points_spinbox,
            self.interval_spinbox,
            self.slices_spinbox,
            self.laser_duration_spinbox,
        ):
            widget.valueChanged.connect(self._update_estimates)
        self.minimal_interval_checkbox.stateChanged.connect(self._update_estimates)

    def _start_live_engine(self):
        """Creates and starts the LiveEngine and its thread."""
        if self._live_thread and self._live_thread.isRunning():
            return

        self.live_engine = LiveEngine(self.hw_controller)
        self._live_thread = QThread()
        self.live_engine.moveToThread(self._live_thread)

        self._live_thread.started.connect(self.live_engine.run)
        self.live_engine.positions_updated.connect(self.nav_panel.update_positions)
        self.live_engine.new_live_image.connect(self.update_image)
        # This signal now means the engine has fully stopped.
        self.live_engine.stopped.connect(self._on_live_engine_stopped)

        self._live_thread.start()

    def _stop_live_engine(self):
        """Stops the LiveEngine and its thread."""
        if self.live_engine and self._live_thread:
            if self._live_thread.isRunning():
                self.live_engine.stop()
                self._live_thread.quit()
                self._live_thread.wait(2000)  # Wait max 2s

    @Slot()
    def _on_run(self):
        """
        Handles the 'Run' button click.

        This initiates a safe handover from the LiveEngine to the AcquisitionEngine
        by stopping the former and starting the latter sequentially.
        """
        self.live_button.setChecked(False)
        self.live_button.setEnabled(False)
        self.run_button.setEnabled(False)
        self.update_status("Stopping live engine before acquisition...")

        # Connect the live engine's stopped signal to start the acquisition.
        # This ensures the acquisition doesn't start until the live engine is down.
        if self.live_engine:
            self.live_engine.stopped.connect(self._start_acquisition_sequence)
        self._stop_live_engine()

    @Slot()
    def _start_acquisition_sequence(self):
        """
        Starts the acquisition. This is called only after the LiveEngine has
        confirmed it has stopped.
        """
        # Assign to a local variable to help the type checker.
        engine = self.live_engine
        if engine is not None:
            # Disconnect the temporary signal to avoid re-triggering.
            engine.stopped.disconnect(self._start_acquisition_sequence)

        self.update_status("Starting acquisition...")
        settings = self._get_settings_from_gui()
        self.acq_engine = AcquisitionEngine(self.hw_controller, settings)
        self._acq_thread = QThread()
        self.acq_engine.moveToThread(self._acq_thread)

        self._acq_thread.started.connect(self.acq_engine.run_acquisition)
        self.acq_engine.acquisition_finished.connect(self.on_acquisition_finished)
        self.acq_engine.new_image_ready.connect(self.update_image)
        self.acq_engine.status_updated.connect(self.update_status)

        self.run_button.setHidden(True)
        self.cancel_button.setHidden(False)
        self._acq_thread.start()

    @Slot()
    def _on_cancel(self):
        if self.acq_engine:
            self.acq_engine.cancel()
        self.cancel_button.setEnabled(False)
        self.update_status("Cancelling...")

    @Slot(bool)
    def _on_live_toggled(self, checked: bool):
        if not self.live_engine:
            return
        if checked:
            self.live_engine.start_live_view(self.live_exposure_spinbox.value())
        else:
            self.live_engine.stop_live_view()

    @Slot()
    def _on_live_engine_stopped(self):
        """Slot for when the live engine's run loop has fully exited."""
        print("GUI notified that Live Engine has stopped.")
        # This is primarily for the acquisition handover, but can be used
        # for other cleanup if needed.

    @Slot(str)
    def _on_browse(self):
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
    def update_image(self, image_8bit: np.ndarray):
        """
        Converts a normalized 8-bit numpy array to a QPixmap for display.
        This method is fast and memory-safe.
        """
        h, w = image_8bit.shape
        # The worker thread now sends a normalized uint8 array.
        # We can display it directly without any further processing.
        q_image = QImage(image_8bit.data, w, h, w, QImage.Format.Format_Grayscale8)

        # Use .copy() to force a deep copy into Qt-managed memory. This is
        # essential to prevent memory leaks and crashes.
        pixmap = QPixmap.fromImage(q_image.copy())

        self.image_display.setPixmap(
            pixmap.scaled(
                self.image_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )

    @Slot(str)
    def update_status(self, message: str):
        self.status_bar.showMessage(message)

    @Slot()
    def on_acquisition_finished(self):
        """Cleans up after an acquisition and restarts the live engine."""
        if self._acq_thread:
            self._acq_thread.quit()
            self._acq_thread.wait()
        self.run_button.setHidden(False)
        self.cancel_button.setHidden(True)
        self.cancel_button.setEnabled(True)
        self.run_button.setEnabled(True)
        self.live_button.setEnabled(True)
        self.status_bar.showMessage("Ready")
        # Restart the live engine for position polling.
        self._start_live_engine()

    def closeEvent(self, event: QCloseEvent):
        """Ensures all engines are stopped cleanly when the window is closed."""
        if self.acq_engine and self.acq_engine._is_running:
            self._on_cancel()
            self.on_acquisition_finished()

        self._stop_live_engine()
        event.accept()
