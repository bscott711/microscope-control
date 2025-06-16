# src/microscope/ui/main_window.py
import logging
import sys
import time

import numpy as np
from magicgui import magicgui
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# --- MODIFIED: Removed unused HardwareConstants import ---
from ..config import AcquisitionSettings, TriggerMode
from ..core.engine import AcquisitionEngine
from ..hardware.hal import HardwareAbstractionLayer, mmc
from .qt_logger import QtLogger


@magicgui(
    call_button=False,
    layout="form",
    save_dir={"widget_type": "FileEdit", "mode": "d", "label": "Save Directory"},
    num_time_points={"label": "Time Points"},
    time_interval_s={"label": "Interval (s)"},
    minimal_interval={"label": "Minimal Interval"},
    num_slices={"label": "Slices/Volume"},
    laser_trig_duration_ms={"label": "Laser Duration (ms)"},
    step_size_um={"label": "Step Size (µm)"},
    should_save={"label": "Save to Disk"},
    save_prefix={"label": "File Prefix"},
)
def acquisition_widget(
    num_time_points: int = 1,
    time_interval_s: float = 0.0,
    minimal_interval: bool = True,
    num_slices: int = 3,
    laser_trig_duration_ms: float = 10.0,
    step_size_um: float = 1.0,
    should_save: bool = False,
    save_dir="",
    save_prefix: str = "acquisition",
):
    """Magicgui widget for acquisition parameters."""
    pass


class AcquisitionGUI(QMainWindow):
    def __init__(self, hal: HardwareAbstractionLayer):
        super().__init__()
        self.hal = hal
        self.settings = AcquisitionSettings()
        self.setWindowTitle("ASI OPM Acquisition Control")
        self.setMinimumSize(800, 700)

        self.acquisition_in_progress = False
        self.cancel_requested = False
        self.pixel_size_um = 1.0
        self.engine = None
        self.acquisition_thread = None
        self._snap_thread = None
        self._snap_worker = None
        self._validated_test_thread = None
        self._validated_test_worker = None

        self._create_main_widgets()
        self._layout_widgets()
        self._setup_logging()

        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self._on_live_timer)
        self.live_timer.setInterval(int(self.settings.camera_exposure_ms))

        self._connect_signals()
        self._update_all_estimates()
        logging.info("Application started.")

    class SnapWorker(QObject):
        finished = Signal()
        image_snapped = Signal(np.ndarray)

        @Slot()
        def run(self):
            try:
                mmc.snapImage()
                image = mmc.getImage()
                self.image_snapped.emit(image)
            except Exception as e:
                logging.error(f"Error during snap worker: {e}")
            finally:
                self.finished.emit()

    class ValidatedTestWorker(QObject):
        finished = Signal()
        status = Signal(str)
        image_ready = Signal(np.ndarray)

        def __init__(self, hal: HardwareAbstractionLayer, settings: AcquisitionSettings):
            super().__init__()
            self.hal = hal
            self.settings = settings

        @Slot()
        def run(self):
            try:
                for image in self.hal.run_validated_test(self.settings):
                    self.image_ready.emit(image)
                    time.sleep(0.01)
                self.status.emit("Validated test finished successfully.")
            except Exception as e:
                self.status.emit(f"Error in validated test: {e}")
                logging.error(f"Error in validated test: {e}")
            finally:
                self.finished.emit()

    def _create_main_widgets(self):
        """Creates all the widgets for the main window."""
        self.controls_widget = acquisition_widget.native
        self.estimates_widget = self._create_estimates_widget()
        self.image_display = QLabel("Camera Image")
        self.image_display.setMinimumSize(512, 512)
        self.image_display.setStyleSheet("background-color: black;")
        self.image_display.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.snap_button = QPushButton("Snap")
        self.live_button = QPushButton("Live")
        self.live_button.setCheckable(True)
        self.run_button = QPushButton("Run Time Series")
        self.validated_test_button = QPushButton("Run Validated Test")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)

        # Create the dropdown for trigger modes
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItems([mode.value for mode in TriggerMode])
        self.trigger_mode_combo.setCurrentText(self.settings.trigger_mode.value)

        # Create a new QHBoxLayout to act as a form row
        row_layout = QHBoxLayout()
        row_layout.addWidget(QLabel("Trigger Mode:"))
        row_layout.addWidget(self.trigger_mode_combo)

        # Add the new row (as a layout) to the controls widget's main QVBoxLayout
        self.controls_widget.layout().addLayout(row_layout)

    def _create_estimates_widget(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout()
        widget.setLayout(layout)
        self.cam_exposure_label = QLabel()
        self.min_interval_label = QLabel()
        self.total_time_label = QLabel()
        layout.addRow("Camera Exposure:", self.cam_exposure_label)
        layout.addRow("Min. Interval/Volume:", self.min_interval_label)
        layout.addRow("Est. Total Time:", self.total_time_label)
        return widget

    def _layout_widgets(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        grid_layout = QGridLayout()
        grid_layout.addWidget(self.controls_widget, 0, 0)
        grid_layout.addWidget(self.estimates_widget, 0, 1)
        main_layout.addLayout(grid_layout)

        middle_section_layout = QHBoxLayout()
        middle_section_layout.addWidget(self.image_display)
        log_layout = QVBoxLayout()
        log_layout.addWidget(QLabel("Log:"))
        log_layout.addWidget(self.log_widget)
        middle_section_layout.addLayout(log_layout)
        middle_section_layout.setStretchFactor(self.image_display, 3)
        middle_section_layout.setStretchFactor(log_layout, 2)
        main_layout.addLayout(middle_section_layout)
        main_layout.setStretchFactor(middle_section_layout, 1)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.snap_button)
        button_layout.addWidget(self.live_button)
        button_layout.addStretch()
        button_layout.addWidget(self.validated_test_button)
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

    def _setup_logging(self):
        self.log_handler = QtLogger(self)
        self.log_handler.new_log_entry.connect(self.log_widget.appendPlainText)
        log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        self.log_handler.setFormatter(log_format)
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_handler)
        root_logger.setLevel(logging.INFO)
        sys.stdout = self.log_handler
        sys.stderr = self.log_handler

    def _connect_signals(self):
        """Connects widget signals to their corresponding slots."""
        self.snap_button.clicked.connect(self._on_snap)
        self.live_button.toggled.connect(self._on_live_toggled)
        self.run_button.clicked.connect(self.start_time_series)
        self.validated_test_button.clicked.connect(self._on_run_validated_test)
        self.cancel_button.clicked.connect(self._request_cancel)
        acquisition_widget.changed.connect(self._update_all_estimates)
        self.trigger_mode_combo.currentTextChanged.connect(self._update_all_estimates)

    @Slot()
    def _update_all_estimates(self):
        """Update the AcquisitionSettings object from all GUI controls."""
        params = acquisition_widget.asdict()
        self.settings.time_points = params["num_time_points"]
        self.settings.time_interval_s = params["time_interval_s"]
        self.settings.is_minimal_interval = params["minimal_interval"]
        self.settings.num_slices = params["num_slices"]
        self.settings.laser_trig_duration_ms = params["laser_trig_duration_ms"]
        self.settings.step_size_um = params["step_size_um"]
        self.settings.should_save = params["should_save"]
        self.settings.save_dir = str(params["save_dir"])
        self.settings.save_prefix = params["save_prefix"]

        # Get the new mode from the dropdown
        new_mode = TriggerMode(self.trigger_mode_combo.currentText())

        # Check if the mode has actually changed before updating and logging
        if self.settings.trigger_mode != new_mode:
            self.settings.trigger_mode = new_mode
            logging.info(f"Trigger mode set to: {new_mode.value}")

        # Update labels
        exposure = self.settings.camera_exposure_ms
        self.cam_exposure_label.setText(f"{exposure:.2f} ms")
        self.live_timer.setInterval(int(exposure))
        min_interval_s = self._calculate_minimal_interval()
        self.min_interval_label.setText(f"{min_interval_s:.2f} s")
        self.total_time_label.setText(self._calculate_total_time(min_interval_s, self.settings.time_points))

    def _calculate_minimal_interval(self) -> float:
        exposure_ms = self.settings.camera_exposure_ms * self.settings.num_slices
        return (exposure_ms * 1.10) / 1000.0

    def _calculate_total_time(self, min_interval_s: float, num_time_points: int) -> str:
        interval = (
            min_interval_s if self.settings.is_minimal_interval else max(self.settings.time_interval_s, min_interval_s)
        )
        total_seconds = interval * num_time_points
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    @Slot()
    def start_time_series(self):
        if self.acquisition_in_progress:
            return
        if self.live_button.isChecked():
            self.live_button.setChecked(False)

        try:
            self.pixel_size_um = mmc.getPixelSizeUm() or 1.0
        except Exception:
            self.pixel_size_um = 1.0
            self.statusBar().showMessage("Warning: Could not get pixel size.", 3000)
            logging.warning("Could not get pixel size.")

        self._set_controls_for_acquisition(True)
        self.cancel_requested = False

        self.acquisition_thread = QThread()
        self.engine = AcquisitionEngine(self.hal, self.settings)
        self.engine.moveToThread(self.acquisition_thread)

        self.engine.acquisition_finished.connect(self._finish_time_series)
        self.engine.status_updated.connect(self.statusBar().showMessage)
        self.engine.new_image_ready.connect(self.display_image)

        self.acquisition_thread.started.connect(self.engine.run_acquisition)
        self.engine.acquisition_finished.connect(self.acquisition_thread.quit)
        self.acquisition_thread.finished.connect(self.engine.deleteLater)
        self.acquisition_thread.finished.connect(self.acquisition_thread.deleteLater)

        self.acquisition_thread.start()

    @Slot()
    def _request_cancel(self):
        if self.acquisition_in_progress and self.engine:
            self.statusBar().showMessage("Cancellation requested...")
            logging.info("Cancellation requested by user.")
            self.engine.cancel()

    def _set_controls_for_acquisition(self, is_running: bool):
        self.acquisition_in_progress = is_running
        self.controls_widget.setEnabled(not is_running)
        self.run_button.setEnabled(not is_running)
        self.validated_test_button.setEnabled(not is_running)
        self.live_button.setEnabled(not is_running)
        self.snap_button.setEnabled(not is_running)
        self.cancel_button.setEnabled(is_running)

    @Slot()
    def _finish_time_series(self):
        status = "Cancelled" if self.cancel_requested else "Acquisition finished."
        self.statusBar().showMessage(status, 5000)
        logging.info(status)
        self._set_controls_for_acquisition(False)
        self.hal.final_cleanup(self.settings)

    @Slot(np.ndarray)
    def display_image(self, image: np.ndarray):
        h, w = image.shape
        img_min, img_max = image.min(), image.max()
        img_range = (img_max - img_min) or 1
        norm = ((image - img_min) / img_range * 255).astype(np.uint8)

        q_image = QImage(norm.data, w, h, w, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image).scaled(
            self.image_display.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_display.setPixmap(pixmap)

    @Slot()
    def _on_run_validated_test(self):
        if self.acquisition_in_progress:
            return
        self._set_controls_for_acquisition(True)
        self.statusBar().showMessage("Running validated test sequence...")
        logging.info("Starting validated test sequence...")
        thread = QThread()
        worker = self.ValidatedTestWorker(self.hal, self.settings)
        self._validated_test_thread = thread
        self._validated_test_worker = worker
        worker.moveToThread(thread)
        worker.status.connect(self.statusBar().showMessage)
        worker.image_ready.connect(self.display_image)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_validated_test_finished)
        thread.started.connect(worker.run)
        thread.start()

    @Slot()
    def _on_validated_test_finished(self):
        self._set_controls_for_acquisition(False)
        self._validated_test_thread = None
        self._validated_test_worker = None
        logging.info("Validated test finished.")

    @Slot()
    def _on_snap(self):
        if self._snap_thread and self._snap_thread.isRunning():
            return
        self.snap_button.setEnabled(False)
        mmc.setExposure(self.settings.camera_exposure_ms)
        thread = QThread()
        worker = self.SnapWorker()
        self._snap_thread = thread
        self._snap_worker = worker
        worker.moveToThread(thread)
        worker.image_snapped.connect(self._display_snapped_image)
        worker.finished.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_snap_finished)
        thread.started.connect(worker.run)
        thread.start()

    @Slot()
    def _on_snap_finished(self):
        self.snap_button.setEnabled(True)
        self._snap_thread = None
        self._snap_worker = None

    @Slot(np.ndarray)
    def _display_snapped_image(self, image: np.ndarray):
        self.display_image(image)

    @Slot(bool)
    def _on_live_toggled(self, checked: bool):
        if checked:
            if self.acquisition_in_progress:
                self.live_button.setChecked(False)
                return
            try:
                logging.info("Starting live view...")
                mmc.setExposure(self.settings.camera_exposure_ms)
                mmc.startContinuousSequenceAcquisition(0)
                self.live_timer.start()
                self._set_controls_for_live(True)
                self.statusBar().showMessage("Live view running...")
            except Exception as e:
                logging.error(f"Error starting live view: {e}")
                self.live_button.setChecked(False)
        else:
            self.live_timer.stop()
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            self._set_controls_for_live(False)
            self.statusBar().showMessage("Live view stopped.", 3000)
            logging.info("Live view stopped.")

    def _set_controls_for_live(self, is_live: bool):
        self.run_button.setEnabled(not is_live)
        self.validated_test_button.setEnabled(not is_live)
        self.snap_button.setEnabled(not is_live)

    @Slot()
    def _on_live_timer(self):
        if mmc.getRemainingImageCount() > 0:
            image = mmc.getLastImage()
            self.display_image(image)
