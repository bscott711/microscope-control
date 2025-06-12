# microscope/gui.py
import os
import threading
import time
import traceback
from datetime import datetime

import numpy as np
from magicgui import magicgui
from pymmcore_plus.mda.handlers import OMETiffWriter
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
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
        self.cancel_requested = False  # Initialize cancellation flag
        self.pixel_size_um = 1.0

        self._create_main_widgets()
        self._layout_widgets()

        self.live_timer = QTimer()
        self.live_timer.timeout.connect(self._on_live_timer)
        self.live_timer.setInterval(int(self.settings.camera_exposure_ms))

        self._connect_signals()
        self._update_all_estimates()

    def _create_main_widgets(self):
        self.controls_widget = acquisition_widget.native
        self.estimates_widget = self._create_estimates_widget()
        self.image_display = QLabel("Camera Image")
        self.image_display.setMinimumSize(512, 512)
        self.image_display.setStyleSheet("background-color: black;")

        self.snap_button = QPushButton("Snap")
        self.live_button = QPushButton("Live")
        self.live_button.setCheckable(True)
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
        button_layout.addWidget(self.snap_button)
        button_layout.addWidget(self.live_button)
        button_layout.addStretch()
        button_layout.addWidget(self.run_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.setCentralWidget(central_widget)

    def _connect_signals(self):
        self.snap_button.clicked.connect(self._on_snap)
        self.live_button.toggled.connect(self._on_live_toggled)
        self.run_button.clicked.connect(self.start_time_series)
        self.cancel_button.clicked.connect(self._request_cancel)
        acquisition_widget.changed.connect(self._update_all_estimates)

    @Slot()
    def _on_snap(self):
        if self.acquisition_in_progress:
            return

        mmc.setExposure(self.settings.camera_exposure_ms)

        def _snap_thread():
            try:
                mmc.snapImage()
                self.worker.signals.frame_ready.emit(mmc.getImage(), MDAEvent())
            except Exception as e:
                print(f"Error during snap: {e}")

        self.worker = self.AcquisitionWorker(self)
        self.worker.signals.frame_ready.connect(self.display_image)

        snap_thread = threading.Thread(target=_snap_thread)
        snap_thread.start()

    @Slot(bool)
    def _on_live_toggled(self, checked: bool):
        if checked:
            if self.acquisition_in_progress:
                self.live_button.setChecked(False)
                return

            try:
                mmc.setExposure(self.settings.camera_exposure_ms)
                mmc.startContinuousSequenceAcquisition(0)
                self.live_timer.start()
                self.run_button.setEnabled(False)
                self.snap_button.setEnabled(False)
                self.statusBar().showMessage("Live view running...")
            except Exception as e:
                print(f"Error starting live view: {e}")
                self.live_button.setChecked(False)
        else:
            self.live_timer.stop()
            if mmc.isSequenceRunning():
                mmc.stopSequenceAcquisition()
            self.run_button.setEnabled(True)
            self.snap_button.setEnabled(True)
            self.statusBar().showMessage("Live view stopped.", 3000)

    @Slot()
    def _on_live_timer(self):
        if mmc.getRemainingImageCount() > 0:
            image = mmc.getLastImage()
            self.display_image(image, MDAEvent())

    @Slot()
    def _update_all_estimates(self):
        params = acquisition_widget.asdict()
        self.settings.num_slices = params["num_slices"]
        self.settings.laser_trig_duration_ms = params["laser_trig_duration_ms"]
        self.settings.step_size_um = params["step_size_um"]

        exposure = self.settings.camera_exposure_ms
        self.cam_exposure_label.setText(f"{exposure:.2f} ms")
        self.live_timer.setInterval(int(exposure))

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

        if self.live_button.isChecked():
            self.live_button.setChecked(False)

        try:
            self.pixel_size_um = mmc.getPixelSizeUm() or 1.0
        except Exception:
            self.pixel_size_um = 1.0
            self.statusBar().showMessage("Warning: Could not get pixel size.", 3000)

        self._set_controls_enabled(False)
        self.cancel_requested = False  # Reset the flag at the start of an acquisition

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
            self.cancel_requested = True  # CORRECTED: Set the flag
            mmc.stopSequenceAcquisition()

    def _set_controls_enabled(self, enabled: bool):
        self.controls_widget.setEnabled(enabled)
        self.run_button.setEnabled(enabled)
        self.live_button.setEnabled(enabled)
        self.snap_button.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)
        self.acquisition_in_progress = not enabled

    @Slot()
    def _finish_time_series(self):
        # CORRECTED: Base the final status on the cancellation flag
        status = "Cancelled" if self.cancel_requested else "Acquisition finished."
        self.statusBar().showMessage(status, 5000)

        # Ensure the sequence is stopped if it's still running (e.g., due to cancel)
        if mmc.isSequenceRunning():
            mmc.stopSequenceAcquisition()

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
                    # CORRECTED: Check for cancellation at the start of each time point
                    if self.gui.cancel_requested:
                        break

                    self.signals.status.emit(f"Acquiring Time Point {t_point + 1}/{params['num_time_points']}")
                    volume_start_time = time.monotonic()

                    (
                        galvo_amp,
                        galvo_center,
                        num_slices,
                    ) = calculate_galvo_parameters(self.gui.settings)
                    configure_devices_for_slice_scan(self.gui.settings, galvo_amp, galvo_center, num_slices)
                    mmc.setExposure(self.gui.settings.camera_exposure_ms)

                    sequence = self._create_mda_sequence(num_slices)
                    writer = self._setup_writer(t_point, params)
                    if writer:
                        writer.sequenceStarted(sequence)

                    mmc.startSequenceAcquisition(num_slices, 0, True)
                    trigger_slice_scan_acquisition()

                    popped_images = 0
                    while mmc.isSequenceRunning() or mmc.getRemainingImageCount() > 0:
                        # CORRECTED: Check for cancellation within the polling loop
                        if self.gui.cancel_requested:
                            break
                        if mmc.getRemainingImageCount() > 0:
                            tagged_img = mmc.popNextTaggedImage()
                            popped_images += 1

                            event = MDAEvent(
                                index={"t": t_point, "z": popped_images - 1}, # type: ignore
                                metadata=tagged_img.tags,
                            )

                            self.signals.frame_ready.emit(tagged_img.pix, event)

                            if writer:
                                writer.frameReady(tagged_img.pix, event, tagged_img.tags) # type: ignore

                            self.signals.status.emit(f"Time Point {t_point + 1} | Slice {popped_images}/{num_slices}")
                        else:
                            time.sleep(0.005)

                    if writer:
                        writer.sequenceFinished(sequence)

                    is_last_timepoint = t_point == params["num_time_points"] - 1
                    if not is_last_timepoint:
                        _reset_for_next_volume()
                        self._wait_for_interval(params, volume_start_time)

            except Exception:
                traceback.print_exc()
            finally:
                self.signals.finished.emit()

        def _create_mda_sequence(self, num_slices: int) -> MDASequence:
            step_size = self.gui.settings.step_size_um
            z_range = (num_slices - 1) * step_size if num_slices > 1 else 0
            z_plan_dict = {"range": z_range, "step": step_size}
            return MDASequence(z_plan=z_plan_dict) # type: ignore

        def _setup_writer(self, t_point: int, params: dict):
            if not params["should_save"]:
                return None

            save_dir = params["save_dir"]
            prefix = params["save_prefix"]
            if not save_dir or not prefix:
                self.signals.status.emit("Error: Save directory or prefix missing.")
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_T{t_point:04d}_{timestamp}.tif"
            filepath = os.path.join(save_dir, filename)

            return OMETiffWriter(filepath)

        def _wait_for_interval(self, params: dict, start_time: float):
            user_interval = params["time_interval_s"]
            wait_time = 0 if params["minimal_interval"] else max(0, user_interval - (time.monotonic() - start_time))
            # CORRECTED: Check for cancellation again before sleeping
            if not self.gui.cancel_requested:
                self.signals.status.emit(f"Waiting {wait_time:.1f}s for next time point...")
                time.sleep(wait_time)
