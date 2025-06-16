from dataclasses import dataclass
from typing import Optional

# Correct Qt import
from PySide6.QtCore import Signal, Slot
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Superqt widgets
from superqt import QCollapsible, QLabeledDoubleSlider, QLabeledSlider

# Import your config class
from microscope.config import AcquisitionSettings


@dataclass
class Channel:
    """A single channel configuration for an acquisition."""

    name: str
    exposure_ms: float


@dataclass
class ZStack:
    """A single Z-stack configuration for an acquisition."""

    start_um: float
    end_um: float
    step_um: float


class MDAWidget(QWidget):
    """
    Widget to configure and run a Multi-Dimensional Acquisition.
    Uses QLabeledSlider/QDoubleSlider from superqt for better UI layout.
    """

    run_acquisition_requested = Signal(AcquisitionSettings)
    acquisition_canceled = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        # --- Timepoints Group ---
        time_group_content = QGroupBox("Timepoints")
        time_layout = QFormLayout()

        self.num_timepoints = QLabeledSlider(Qt.Orientation.Horizontal)
        self.num_timepoints.setTextLabel("Number:")
        self.num_timepoints.setRange(1, 1000)
        self.num_timepoints.setValue(10)

        self.timepoint_interval = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.timepoint_interval.setTextLabel("Interval:")
        self.timepoint_interval.setRange(0.0, 3600.0)
        self.timepoint_interval.setValue(1.0)
        self.timepoint_interval.setSuffix(" s")

        time_layout.addRow(self.num_timepoints)
        time_layout.addRow(self.timepoint_interval)
        time_group_content.setLayout(time_layout)

        self.time_collapsible = QCollapsible("Timepoints Settings")
        self.time_collapsible.setContent(time_group_content)
        self.time_collapsible.collapse(False)  # Use setChecked instead of setExpanded

        # --- Z-Stack Group ---
        z_group_content = QGroupBox("Z-Stack")
        z_layout = QFormLayout()

        self.z_start = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_start.setTextLabel("Start (µm):")
        self.z_start.setRange(-1000.0, 1000.0)
        self.z_start.setValue(0.0)

        self.z_end = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_end.setTextLabel("End (µm):")
        self.z_end.setRange(-1000.0, 1000.0)
        self.z_end.setValue(10.0)

        self.z_step = QLabeledDoubleSlider(Qt.Orientation.Horizontal)
        self.z_step.setTextLabel("Step (µm):")
        self.z_step.setRange(0.1, 100.0)
        self.z_step.setValue(1.0)

        z_layout.addRow(self.z_start)
        z_layout.addRow(self.z_end)
        z_layout.addRow(self.z_step)
        z_group_content.setLayout(z_layout)

        self.z_collapsible = QCollapsible("Z-Stack Settings")
        self.z_collapsible.setContent(z_group_content)
        self.z_collapsible.collapse(False)

        # --- Control Buttons ---
        self.run_button = QPushButton("Run Acquisition")
        self.run_button.clicked.connect(self._on_run_clicked)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.time_collapsible)
        main_layout.addWidget(self.z_collapsible)
        main_layout.addStretch()
        main_layout.addWidget(self.run_button)
        main_layout.addWidget(self.cancel_button)

    def _on_run_clicked(self):
        settings = self.get_settings()
        self.run_acquisition_requested.emit(settings)

    def _on_cancel_clicked(self):
        self.acquisition_canceled.emit()

    def get_settings(self) -> AcquisitionSettings:
        settings = AcquisitionSettings()

        settings.time_points = self.num_timepoints.value()
        settings.time_interval_s = self.timepoint_interval.value()
        settings.is_minimal_interval = settings.time_interval_s == 0

        z_range = abs(self.z_end.value() - self.z_start.value())
        step = self.z_step.value()
        settings.num_slices = int(round(z_range / step)) + 1 if step > 0 else 1
        settings.step_size_um = step

        # Hardcoded as per original logic
        settings.laser_trig_duration_ms = 100.0

        return settings

    @Slot(bool)
    def set_running_state(self, running: bool):
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
