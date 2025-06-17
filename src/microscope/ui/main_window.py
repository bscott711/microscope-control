# src/microscope/ui/main_window.py
import sys

from pymmcore_widgets import (
    DefaultCameraExposureWidget,
    StageWidget,
)
from PySide6.QtCore import QObject, Signal, Slot
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QMainWindow,
    QPlainTextEdit,
    QStatusBar,
)

from microscope.config import AcquisitionSettings
from microscope.hardware.engine import AcquisitionEngine, AcquisitionState, GalvoPLogicMDA

from .styles import STYLESHEET
from .widgets.mda_widget import MDAWidget
from .widgets.viewer_widget import ViewerWidget


class QtLogHandler(QObject):
    """Redirects stdout/stderr to a Qt signal."""

    new_text = Signal(str)

    def write(self, text: str):
        self.new_text.emit(text)

    def flush(self):
        pass


class MainWindow(QMainWindow):
    """
    The main application window.
    """

    def __init__(self, engine: AcquisitionEngine):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.setStyleSheet(STYLESHEET)

        self.engine = engine
        self.mmc = self.engine.hal.mmc

        self.viewer = ViewerWidget()
        self.setCentralWidget(self.viewer)

        self._create_dock_widgets()
        self._connect_signals()

        if isinstance(sys.stdout, QtLogHandler):
            sys.stdout.new_text.connect(self.log_widget.appendPlainText)

    def _create_dock_widgets(self):
        """Create and arrange all dockable widgets."""
        self.mda_widget = MDAWidget()
        mda_dock = QDockWidget("Acquisition", self)
        mda_dock.setWidget(self.mda_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, mda_dock)

        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        log_dock = QDockWidget("Log", self)
        log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)

        self.demo_mode_checkbox = QCheckBox("Demo Mode")
        self.demo_mode_checkbox.setChecked(True)

        self.status_bar = QStatusBar()
        self.status_bar.addPermanentWidget(self.demo_mode_checkbox)
        self.setStatusBar(self.status_bar)

    def setup_device_widgets(self):
        """Create device-specific widgets after config is loaded."""
        if not self.mmc:
            return

        camera_device = self.mmc.getCameraDevice()
        camera_widget = DefaultCameraExposureWidget(mmcore=self.mmc)
        camera_widget.setEnabled(bool(camera_device))

        focus_device = self.mmc.getFocusDevice()
        stage_widget = StageWidget(device=focus_device)
        stage_widget.setEnabled(bool(focus_device))

        cam_dock = QDockWidget("Camera", self)
        cam_dock.setWidget(camera_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, cam_dock)

        stage_dock = QDockWidget("Stage", self)
        stage_dock.setWidget(stage_widget)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, stage_dock)

        self.tabifyDockWidget(cam_dock, stage_dock)

    @Slot(AcquisitionSettings)
    def _on_run_acquisition(self, settings: AcquisitionSettings):
        """Creates an acquisition plan and starts the engine."""
        plan = GalvoPLogicMDA()
        self.engine.run_acquisition(plan, settings)

    def _connect_signals(self):
        """Connect all signals between the UI and the engine."""
        self.mda_widget.run_acquisition_requested.connect(self._on_run_acquisition)
        self.mda_widget.cancel_button.clicked.connect(self.engine.cancel_acquisition)

        self.engine.signals.state_changed.connect(self._on_engine_state_changed)
        self.engine.signals.frame_acquired.connect(self.viewer.on_new_frame)
        # FIX: Connect the acquisition_error signal to our new dedicated slot.
        self.engine.signals.acquisition_error.connect(self._on_acquisition_error)

    def _on_engine_state_changed(self, state: AcquisitionState):
        """Updates the UI based on the engine's state."""
        message = f"Status: {state.name}"
        print(message)  # This will be redirected to the log widget
        self.update_status(message)

        if state in (AcquisitionState.ACQUIRING, AcquisitionState.PREPARING):
            self.mda_widget.set_running_state(True)
        else:
            self.mda_widget.set_running_state(False)

    # NEW: Dedicated slot for handling and routing error messages.
    @Slot(str)
    def _on_acquisition_error(self, message: str):
        """Displays an error message in the log and status bar."""
        error_message = f"ERROR: {message}"
        print(error_message)  # Redirect to the log widget
        self.update_status(error_message)  # Show in status bar

    def update_status(self, message: str):
        self.status_bar.showMessage(message)
