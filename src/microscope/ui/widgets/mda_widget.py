from dataclasses import dataclass

from PySide6.QtCore import Signal, Slot
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

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
    """Widget to configure and run a Multi-Dimensional Acquisition."""

    run_acquisition_requested = Signal(object)  # Emits AcquisitionSettings

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- Timepoints Group ---
        time_group = QGroupBox("Timepoints")
        time_layout = QFormLayout()
        self.num_timepoints = QSpinBox()
        self.num_timepoints.setValue(10)
        self.timepoint_interval = QDoubleSpinBox()
        self.timepoint_interval.setValue(1.0)
        self.timepoint_interval.setSuffix(" s")
        time_layout.addRow("Number:", self.num_timepoints)
        time_layout.addRow("Interval:", self.timepoint_interval)
        time_group.setLayout(time_layout)

        # --- Z-Stack Group ---
        z_group = QGroupBox("Z-Stack")
        z_layout = QFormLayout()
        self.z_start = QDoubleSpinBox()
        self.z_start.setRange(-1000, 1000)
        self.z_end = QDoubleSpinBox()
        self.z_end.setRange(-1000, 1000)
        self.z_step = QDoubleSpinBox()
        self.z_step.setRange(0.1, 100)
        self.z_step.setValue(1)
        z_layout.addRow("Start:", self.z_start)
        z_layout.addRow("End:", self.z_end)
        z_layout.addRow("Step:", self.z_step)
        z_group.setLayout(z_layout)

        # --- Acquisition Control Buttons ---
        self.run_button = QPushButton("Run Acquisition")
        self.run_button.clicked.connect(self._on_run_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(time_group)
        main_layout.addWidget(z_group)
        main_layout.addStretch()
        main_layout.addWidget(self.run_button)
        main_layout.addWidget(self.cancel_button)

    def _on_run_clicked(self):
        """Emits the acquisition settings when the run button is clicked."""
        settings = self.get_settings()
        self.run_acquisition_requested.emit(settings)

    def get_settings(self) -> AcquisitionSettings:
        """Constructs an AcquisitionSettings object from the UI fields."""
        settings = AcquisitionSettings()

        # Map UI fields to the settings object from config.py
        settings.time_points = self.num_timepoints.value()
        settings.time_interval_s = self.timepoint_interval.value()
        settings.is_minimal_interval = self.timepoint_interval.value() == 0

        settings.num_slices = int(abs(self.z_end.value() - self.z_start.value()) / self.z_step.value()) + 1
        settings.step_size_um = self.z_step.value()

        # Your config.py settings object does not have a concept of channels,
        # but it does have laser_trig_duration_ms. We'll use a hardcoded
        # value for now as the UI doesn't have an exposure field.
        settings.laser_trig_duration_ms = 100.0  # ms

        return settings

    @Slot(bool)
    def set_running_state(self, running: bool):
        """Updates the UI to reflect the acquisition state."""
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
