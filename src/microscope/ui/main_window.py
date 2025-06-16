import sys

from pymmcore_widgets import (
    DefaultCameraExposureWidget,
    ImagePreview,
    StageWidget,
)
from PySide6.QtCore import QObject, Signal  # Corrected import for Signal
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QMainWindow,
    QPlainTextEdit,
    QStatusBar,
)

from ..core.engine import AcquisitionEngine
from .styles import STYLESHEET
from .widgets.mda_widget import MDAWidget


class QtLogHandler(QObject):
    """
    A file-like object that redirects stdout/stderr to a Qt signal.
    """

    new_text = Signal(str)

    def write(self, text: str):
        self.new_text.emit(text)

    def flush(self):
        pass


class MainWindow(QMainWindow):
    """
    The final main application window, arranged in a professional, dockable
    layout precisely matching the target design.
    """

    def __init__(self, engine: AcquisitionEngine):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.setStyleSheet(STYLESHEET)

        self.engine = engine
        self.mmc = self.engine.hal.mmc

        self.viewer = ImagePreview()
        self.setCentralWidget(self.viewer)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.demo_mode_checkbox = QCheckBox("Demo Mode")
        self.status_bar.addPermanentWidget(self.demo_mode_checkbox)

        log_dock = QDockWidget("Log", self)
        self.log_widget = QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        log_dock.setWidget(self.log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, log_dock)

        self._log_handler = QtLogHandler()
        self._log_handler.new_text.connect(self.log_widget.insertPlainText)
        sys.stdout = self._log_handler
        # NOTE: Temporarily disabling stderr redirection to uncover hidden errors
        # sys.stderr = self._log_handler

    def setup_device_widgets(self):
        """
        Creates and arranges widgets that depend on a loaded config file.
        """
        if not self.mmc:
            return

        self.mda_widget = MDAWidget()
        mda_dock = QDockWidget("Multi-D Acquisition", self)
        mda_dock.setWidget(self.mda_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, mda_dock)

        camera_widget = DefaultCameraExposureWidget()

        focus_device = self.mmc.getFocusDevice()
        stage_widget = StageWidget(device=focus_device)
        stage_widget.setEnabled(bool(focus_device))

        cam_dock = QDockWidget("Camera", self)
        cam_dock.setWidget(camera_widget)
        stage_dock = QDockWidget("Stage", self)
        stage_dock.setWidget(stage_widget)

        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, cam_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, stage_dock)

        # Corrected tabbing to only include remaining widgets
        self.tabifyDockWidget(cam_dock, stage_dock)

        self._connect_custom_engine()

    def update_status(self, message: str):
        self.status_bar.showMessage(message)

    def _connect_custom_engine(self):
        """Connects the MDA widget to our custom hardware-timed engine."""
        self.mda_widget.run_acquisition_requested.connect(self.engine.run_acquisition)
        self.mda_widget.cancel_button.clicked.connect(self.engine.cancel_acquisition)

        self.engine.signals.acquisition_started.connect(lambda: self.mda_widget.set_running_state(True))
        self.engine.signals.acquisition_finished.connect(lambda: self.mda_widget.set_running_state(False))

    def closeEvent(self, event):
        """Ensure safe shutdown."""
        self.engine.cancel_acquisition()
        if self.mmc and self.mmc.getLoadedDevices():
            self.mmc.reset()
        super().closeEvent(event)
