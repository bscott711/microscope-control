# src/microscope/ui/widgets/mda_widget.py
from typing import Optional

from PySide6.QtCore import Signal
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from superqt import QLabeledDoubleSlider, QLabeledSlider

from microscope.config import AcquisitionSettings, Channel, ZStack


class MDAWidget(QWidget):
    """
    Widget to configure and run a Multi-Dimensional Acquisition.
    This has been updated to use the centralized AcquisitionSettings from config.py.
    """

    run_acquisition_requested = Signal(AcquisitionSettings)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # --- Timepoints Group ---
        time_group = QGroupBox("Timepoints")
        time_layout = QFormLayout(time_group)
        self.num_timepoints = QLabeledSlider(Qt.Orientation.Horizontal)
        self.num_timepoints.setRange(1, 100)
        self.timepoint_interval = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.timepoint_interval.setRange(0, 60)
        time_layout.addRow("Number:", self.num_timepoints)
        time_layout.addRow("Interval (s):", self.timepoint_interval)

        # --- Z-Stack Group ---
        z_group = QGroupBox("Z-Stack")
        z_layout = QFormLayout(z_group)
        self.z_start = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_start.setRange(-50, 50)
        self.z_end = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_end.setRange(-50, 50)
        self.z_step = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_step.setRange(0.1, 5)
        self.z_step.setValue(1.0)
        z_layout.addRow("Start (µm):", self.z_start)
        z_layout.addRow("End (µm):", self.z_end)
        z_layout.addRow("Step (µm):", self.z_step)

        # --- Run/Cancel Buttons ---
        self.run_button = QPushButton("Run Acquisition")
        self.run_button.clicked.connect(self._on_run_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(time_group)
        main_layout.addWidget(z_group)
        main_layout.addStretch()
        main_layout.addWidget(self.run_button)
        main_layout.addWidget(self.cancel_button)

    def _on_run_clicked(self):
        settings = self.get_settings()
        self.run_acquisition_requested.emit(settings)

    def get_settings(self) -> AcquisitionSettings:
        """Constructs the AcquisitionSettings object from the UI fields."""
        # Create a ZStack object if the step size is greater than 0
        z_stack = None
        if self.z_step.value() > 0:
            z_stack = ZStack(
                start_um=self.z_start.value(),
                end_um=self.z_end.value(),
                step_um=self.z_step.value(),
            )

        # NOTE: Channels are hardcoded for now as there's no UI for them.
        # This could be expanded with a channel table or list widget.
        channels = [Channel(name="488nm", exposure_ms=10.0)]

        return AcquisitionSettings(
            channels=channels,
            z_stack=z_stack,
            time_points=self.num_timepoints.value(),
            time_interval_s=self.timepoint_interval.value(),
        )

    def set_running_state(self, is_running: bool):
        """Disables UI elements when an acquisition is running."""
        self.run_button.setEnabled(not is_running)
        self.cancel_button.setEnabled(is_running)
        self.z_start.setEnabled(not is_running)
        self.z_end.setEnabled(not is_running)
        self.z_step.setEnabled(not is_running)
        self.num_timepoints.setEnabled(not is_running)
        self.timepoint_interval.setEnabled(not is_running)
