# microscope/gui.py
import os
import time
import traceback
from datetime import datetime

import numpy as np
from magicgui import magicgui
from pymmcore_plus.mda import mda_listeners_connected
from pymmcore_plus.mda.handlers import OMETiffWriter
from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from useq import MDAEvent, MDASequence

from .config import AcquisitionSettings
from .hardware_control import (
    HardwareInterface,
    _reset_for_next_volume,
    calculate_galvo_parameters,
    configure_devices_for_slice_scan,
    final_cleanup,
    mmc,
    trigger_slice_scan_acquisition,
)


class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""

    finished = Signal()
    error = Signal(tuple)
    status = Signal(str)
    frame_ready = Signal(np.ndarray, MDAEvent)


# CORRECTED: Explicitly set the widget_type for `save_dir` to 'FileEdit'
# to ensure it can accept the `mode='d'` argument.
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
    time_interval_s: float = 10.0,
    minimal_interval: bool = False,
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
    def __init__(self, hw_interface: HardwareInterface):
        super().__init__()
        self.hw_interface = hw_interface
        self.settings = AcquisitionSettings()
        self.setWindowTitle("ASI OPM Acquisition Control")
        self.setMinimumSize(600, 700)

        self.acquisition_in_progress = False
        self.pixel_size_um = 1.0

        self._create_main_widgets()
        self._layout_widgets()
        self._connect_signals()
        self._update_all_estimates()

    def _create_main_widgets(self):
        self.controls_widget = acquisition_widget.native
        self.estimates_widget = self._create_estimates_widget()
        self.image_display = QLabel("Camera Image")
        self.image_display.setMinimumSize(512, 512)
        self.image_display.setStyleSheet("background-color: black;")
        self.run_button = QPushButton("Run Time Series")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

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
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        grid_layout = QGridLayout()
        grid_layout.addWidget(self.controls_widget, 0, 0)
        grid_layout.addWidget(self.estimates_widget, 0, 1)
        main_layout.addLayout(grid_layout)
        main_layout.addWidget(self.image_display)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        self.setCentralWidget(central_widget)

    def _connect_signals(self):
        self.run_button.clicked.connect(self.start_time_series)
        self.cancel_button.clicked.connect(self._request_cancel)
        acquisition_widget.changed.connect(self._update_all_estimates)

    @Slot()
    def _update_all_estimates(self):
        params = acquisition_widget.asdict()
        self.settings.num_slices = params["num_slices"]
        self.settings.laser_trig_duration_ms = params["laser_trig_duration_ms"]
        self.settings.step_size_um = params["step_size_um"]
        self.cam_exposure_label.setText(f"{self.settings.camera_exposure_ms:.2f} ms")
        min_interval_s = self._calculate_minimal_interval()
        self.min_interval_label.setText(f"{min_interval_s:.2f} s")
        self.total_time_label.setText(self._calculate_total_time(min_interval_s, params["num_time_points"]))

    def _calculate_minimal_interval(self) -> float:
        exposure_ms = self.settings.camera_exposure_ms * self.settings.num_slices
        return (exposure_ms * 1.10) / 1000.0

    def _calculate_total_time(self, min_interval_s: float, num_time_points: int) -> str:
        params = acquisition_widget.asdict()
        interval = min_interval_s if params["minimal_interval"] else max(params["time_interval_s"], min_interval_s)
        total_seconds = interval * num_time_points
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

    @Slot()
    def start_time_series(self):
        if self.acquisition_in_progress:
            return
        try:
            self.pixel_size_um = mmc.getPixelSizeUm() or 1.0
        except Exception:
            self.pixel_size_um = 1.0
            self.statusBar().showMessage("Warning: Could not get pixel size.", 3000)
        self._set_controls_enabled(False)

        self.acquisition_thread = QThread()
        self.worker = self.AcquisitionWorker(self)
        self.worker.moveToThread(self.acquisition_thread)

        self.worker.signals.finished.connect(self.acquisition_thread.quit)
        self.worker.signals.finished.connect(self.worker.deleteLater)
        self.acquisition_thread.finished.connect(self.acquisition_thread.deleteLater)
        self.worker.signals.status.connect(self.statusBar().showMessage)
        self.worker.signals.frame_ready.connect(self.display_image)
        self.worker.signals.finished.connect(self._finish_time_series)

        self.acquisition_thread.started.connect(self.worker.run)
        self.acquisition_thread.start()

    @Slot()
    def _request_cancel(self):
        if self.acquisition_in_progress:
            self.statusBar().showMessage("Cancellation requested...")
            mmc.mda.cancel()

    def _set_controls_enabled(self, enabled: bool):
        self.controls_widget.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)
        self.acquisition_in_progress = not enabled

    @Slot()
    def _finish_time_series(self):
        status = "Cancelled" if mmc.mda.is_paused() else "Acquisition finished."
        self.statusBar().showMessage(status, 5000)
        self._set_controls_enabled(True)
        final_cleanup(self.settings)
        self.hw_interface.find_and_set_trigger_mode(self.hw_interface.camera1, ["Internal", "Internal Trigger"])

    @Slot(np.ndarray, MDAEvent)
    def display_image(self, image: np.ndarray, event: MDAEvent):
        h, w = image.shape
        norm = ((image - image.min()) / (image.max() or 1) * 255).astype(np.uint8)
        q_image = QImage(norm.data, w, h, w, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image).scaled(
            self.image_display.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_display.setPixmap(pixmap)

    class AcquisitionWorker(QObject):
        signals = WorkerSignals()

        def __init__(self, gui_instance):
            super().__init__()
            self.gui = gui_instance

        @Slot()
        def run(self):
            try:
                params = acquisition_widget.asdict()
                mmc.setCameraDevice(self.gui.hw_interface.camera1)
                for t_point in range(params["num_time_points"]):
                    if mmc.mda.is_paused():
                        break
                    self.signals.status.emit(f"Running Time Point {t_point + 1}/{params['num_time_points']}")
                    volume_start_time = time.monotonic()
                    sequence = self._create_mda_sequence()
                    writer = self._setup_writer(t_point, params)
                    handlers = [self._setup_plogic, self.signals.frame_ready]
                    if writer:
                        handlers.append(writer)
                    with mda_listeners_connected(*handlers):
                        mmc.run_mda(sequence)
                    _reset_for_next_volume()
                    self._wait_for_interval(t_point, params, volume_start_time)
            except Exception:
                traceback.print_exc()
            finally:
                self.signals.finished.emit()

        def _create_mda_sequence(self) -> MDASequence:
            _, _, num_slices = calculate_galvo_parameters(self.gui.settings)
            z_plan_dict = {
                "steps": num_slices,
                "step": self.gui.settings.step_size_um,
            }
            sequence = MDASequence(z_plan=z_plan_dict)  # type: ignore
            return sequence

        def _setup_writer(self, t_point: int, params: dict):
            if not params["should_save"]:
                return None
            save_dir = params["save_dir"]
            prefix = params["save_prefix"]
            if not save_dir or not prefix:
                self.signals.status.emit("Error: Save directory or prefix missing.")
                return None
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_T{t_point + 1:04d}_{timestamp}.tif"
            filepath = os.path.join(save_dir, filename)
            return OMETiffWriter(filepath)

        def _setup_plogic(self, event: MDAEvent):
            if event.index.get("z", 0) == 0:
                (
                    galvo_amp,
                    galvo_center,
                    num_slices,
                ) = calculate_galvo_parameters(self.gui.settings)
                configure_devices_for_slice_scan(self.gui.settings, galvo_amp, galvo_center, num_slices)
                mmc.setExposure(self.gui.settings.camera_exposure_ms)
                trigger_slice_scan_acquisition()

        def _wait_for_interval(self, t_point: int, params: dict, start_time: float):
            if t_point < params["num_time_points"] - 1:
                user_interval = params["time_interval_s"]
                wait_time = 0 if params["minimal_interval"] else max(0, user_interval - (time.monotonic() - start_time))
                self.signals.status.emit(f"Waiting {wait_time:.1f}s for next time point...")
                time.sleep(wait_time)
