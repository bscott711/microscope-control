# src/microscope/ui/main_window.py

from datetime import timedelta
from typing import Any

import numpy as np
import useq
from pymmcore_plus import CMMCorePlus
from pymmcore_widgets import (
    ChannelWidget,
    CoreLogWidget,
    DefaultCameraExposureWidget,
    ImagePreview,
    LiveButton,
    MDAWidget,
    ObjectivesWidget,
    SnapButton,
    StageWidget,
)
from PySide6.QtCore import Signal, Slot
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDockWidget,
    QGridLayout,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from microscope.config import AcquisitionSettings, Channel, ZStack
from microscope.hardware.engine import (
    AcquisitionEngine,
    AcquisitionState,
    GalvoPLogicMDA,
)

from .styles import STYLESHEET


class CustomMDAWidget(MDAWidget):
    """
    A subclass of MDAWidget that allows a custom acquisition engine to be used.
    """
    # FIX: Explicitly declare the signals to make them known to Pylance.
    started = Signal(useq.MDASequence)
    stop_requested = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        run_button = self.findChild(QPushButton, "run_button")
        stop_button = self.findChild(QPushButton, "stop_button")
        if run_button:
            run_button.clicked.disconnect()
            run_button.clicked.connect(self._on_run_clicked)
        if stop_button:
            stop_button.clicked.disconnect()
            stop_button.clicked.connect(self.stop_requested.emit)

    @Slot()
    def _on_run_clicked(self) -> None:
        if seq := self.value():
            self.started.emit(seq)


class MainWindow(QMainWindow):
    """The main application window, with all type-checking errors fixed."""

    _running_sequence: useq.MDASequence | None = None

    def __init__(self, engine: AcquisitionEngine):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.setStyleSheet(STYLESHEET)

        self.engine = engine
        if not isinstance(engine.hal.mmc, CMMCorePlus):
            raise TypeError("Engine's HAL must have a valid CMMCorePlus instance.")
        self.mmc: CMMCorePlus = engine.hal.mmc

        # Create widgets
        self.viewer = ImagePreview()
        self.setCentralWidget(self.viewer)
        self.mda_widget = CustomMDAWidget()
        self.log_widget = CoreLogWidget()

        # Arrange widgets
        mda_dock = QDockWidget("MDA", self)
        mda_dock.setWidget(self.mda_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, mda_dock)

        log_dock = QDockWidget("Log", self)
        log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self._setup_hardware_widgets()
        self.connect_signals()

    def _setup_hardware_widgets(self):
        """Creates dock widgets with tabbed hardware controls."""
        hw_dock = QDockWidget("Hardware Controls", self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, hw_dock)
        tabs = QTabWidget()
        hw_dock.setWidget(tabs)

        # -- Live Controls Tab --
        live_tab = QWidget()
        live_layout = QGridLayout(live_tab)
        live_layout.setContentsMargins(10, 10, 10, 10)
        tabs.addTab(live_tab, "Live")

        live_layout.addWidget(SnapButton(), 0, 0)
        live_layout.addWidget(LiveButton(), 0, 1)
        live_layout.addWidget(DefaultCameraExposureWidget(), 1, 0, 1, 2)
        live_layout.addWidget(ChannelWidget(), 2, 0, 1, 2)
        live_layout.setRowStretch(3, 1)

        # -- Stage/Objectives Tab --
        stage_tab = QWidget()
        stage_layout = QVBoxLayout(stage_tab)
        stage_layout.setContentsMargins(10, 10, 10, 10)
        tabs.addTab(stage_tab, "Stage")

        try:
            stage_device_label = self.mmc.getXYStageDevice()
            if stage_device_label:
                stage_layout.addWidget(StageWidget(device=stage_device_label))
        except Exception as e:
            print(f"WARNING: Could not create stage widget: {e}")
        try:
            stage_layout.addWidget(ObjectivesWidget())
        except Exception as e:
            print(f"WARNING: Could not create objectives widget: {e}")
        stage_layout.addStretch()

    def connect_signals(self):
        """Connect all signals between the UI and the engine."""
        self.mda_widget.started.connect(self._on_run_clicked)
        self.mda_widget.stop_requested.connect(self.engine.cancel_acquisition)
        self.engine.signals.state_changed.connect(self._on_engine_state_changed)

    @Slot(useq.MDASequence)
    def _on_run_clicked(self, sequence: useq.MDASequence):
        """Called when the MDA widget's 'started' signal is emitted."""
        self._running_sequence = sequence
        settings = self._convert_sequence_to_settings(sequence)
        self.engine.run_acquisition(GalvoPLogicMDA(), settings)

    def _convert_sequence_to_settings(
        self, sequence: useq.MDASequence
    ) -> AcquisitionSettings:
        """Robustly converts a useq.MDASequence to the engine's AcquisitionSettings."""
        z_stack = None
        if z_plan := sequence.z_plan:
            positions = np.array(list(z_plan))
            if len(positions) > 1:
                step = np.abs(np.diff(positions)).mean() if len(positions) > 1 else 0
                z_stack = ZStack(
                    start_um=positions.min(), end_um=positions.max(), step_um=step
                )

        default_exposure = self.mmc.getExposure()
        channels = [
            Channel(name=ch.config, exposure_ms=ch.exposure or default_exposure)
            for ch in sequence.channels
        ]

        num_timepoints = 1
        time_interval_s = 0.0
        if time_plan := sequence.time_plan:
            if isinstance(time_plan, useq.TIntervalLoops):
                num_timepoints = time_plan.loops
                time_interval_s = time_plan.interval.total_seconds()
            else:
                points = list(time_plan)
                num_timepoints = len(points)
                if num_timepoints > 1:
                    p1 = points[0]
                    p2 = points[1]
                    td1 = p1[1] if isinstance(p1, tuple) else p1
                    td2 = p2[1] if isinstance(p2, tuple) else p2

                    def to_seconds(t: Any) -> float:
                        if isinstance(t, timedelta):
                            return t.total_seconds()
                        return float(t)

                    time_interval_s = to_seconds(td2) - to_seconds(td1)

        return AcquisitionSettings(
            channels=channels,
            z_stack=z_stack,
            time_points=num_timepoints,
            time_interval_s=time_interval_s,
        )

    @Slot(AcquisitionState)
    def _on_engine_state_changed(self, state: AcquisitionState):
        """Updates the UI based on the engine's state."""
        message = f"Status: {state.name}"
        self.status_bar.showMessage(message)
        print(message)

        is_running = state in (AcquisitionState.ACQUIRING, AcquisitionState.PREPARING)

        if self._running_sequence:
            if is_running:
                self.mda_widget._on_mda_started()
            else:
                # FIX: Add the sequence argument back to this call.
                self.mda_widget._on_mda_finished(self._running_sequence)
                self._running_sequence = None
