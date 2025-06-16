# Import all necessary pre-built widgets from the library
from pymmcore_widgets import (
    ConfigurationWidget,
    ImagePreview,
    MDAWidget,
    StageWidget,
)
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget, QMainWindow

from microscope.core.engine import AcquisitionEngine
from microscope.hardware.hal import HardwareAbstractionLayer

from .styles import STYLESHEET


class MainWindow(QMainWindow):
    """
    The final main application window, arranged in a professional, dockable
    layout precisely matching the target design.
    """

    def __init__(self, mmc):
        super().__init__()
        self.setWindowTitle("Microscope Control")
        self.setStyleSheet(STYLESHEET)
        self.mmc = mmc

        # --- Initialize Core and Hardware Layers ---
        self.hal = HardwareAbstractionLayer(self.mmc)
        self.engine = AcquisitionEngine(self.hal)

        # --- Create and Arrange Library Widgets ---

        # 1. Set the ImagePreview as the central widget
        self.viewer = ImagePreview()
        self.setCentralWidget(self.viewer)

        # 2. Create the MDA widget and dock it on the right
        self.mda_widget = MDAWidget()
        mda_dock = QDockWidget("Multi-D Acquisition", self)
        mda_dock.setWidget(self.mda_widget)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, mda_dock)

        # 3. Create the left-side control widgets
        camera_widget = DefaultCameraWidget()
        stage_widget = StageWidget()
        # The ConfigurationWidget is used for both Objectives and Channels
        # by pointing it to the correct group from the config file.
        objectives_widget = ConfigurationWidget("Objective")
        channels_widget = ConfigurationWidget("Channel")

        # 4. Create docks for each left-side widget
        cam_dock = QDockWidget("Camera", self)
        cam_dock.setWidget(camera_widget)

        stage_dock = QDockWidget("Stage", self)
        stage_dock.setWidget(stage_widget)

        obj_dock = QDockWidget("Objectives", self)
        obj_dock.setWidget(objectives_widget)

        channel_dock = QDockWidget("Channels", self)
        channel_dock.setWidget(channels_widget)

        # 5. Add the docks to the window, stacking them on the left
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, cam_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, stage_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, obj_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, channel_dock)

        # 6. Tabify the stacked dock widgets to match the target UI
        self.tabifyDockWidget(cam_dock, stage_dock)
        self.tabifyDockWidget(stage_dock, obj_dock)

        # --- Connect our custom engine to the MDA widget ---
        self._connect_custom_engine()

    def _connect_custom_engine(self):
        """Connects the MDA widget to our custom hardware-timed engine."""
        # Disconnect the library widget's default run behavior
        self.mda_widget.run_mda_button.clicked.disconnect()
        # Connect the button to our custom run method
        self.mda_widget.run_mda_button.clicked.connect(self._run_custom_mda)

        # Connect signals from our engine back to the widget's UI slots
        self.engine.signals.acquisition_progress.connect(self.mda_widget.mda_progress.setValue)
        self.engine.signals.acquisition_finished.connect(self.mda_widget._on_mda_finished)

    def _run_custom_mda(self):
        """Translates the sequence from the UI widget and runs our engine."""
        from microscope.config import AcquisitionSettings, Channel, ZStack

        sequence = self.mda_widget.get_state()

        settings = AcquisitionSettings()
        if sequence.time_plan:
            settings.num_timepoints = sequence.time_plan.loops
            settings.timepoint_interval_s = sequence.time_plan.interval.total_seconds()
        if sequence.z_plan:
            settings.z_stack = ZStack(
                start_um=sequence.z_plan.start, end_um=sequence.z_plan.top, step_um=sequence.z_plan.step
            )
        settings.channels = [Channel(name=ch.config, exposure_ms=ch.exposure) for ch in sequence.channels]

        self.engine.run_acquisition(settings)

    def closeEvent(self, event):
        """Ensure safe shutdown."""
        self.engine.cancel_acquisition()
        self.mmc.reset()
        super().closeEvent(event)
