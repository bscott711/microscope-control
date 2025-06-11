# src/microscope/navigation_panel.py
"""
Navigation Panel GUI

This module contains the self-contained NavigationPanel widget, which provides
all the necessary controls for moving the microscope stages and galvos.
"""

from functools import partial

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


class AxisControlWidget(QWidget):
    """A reusable widget for controlling a single hardware axis."""

    # --- Signals ---
    move_to_requested = Signal(float)
    move_by_requested = Signal(float)
    jog_started = Signal(float)
    jog_stopped = Signal()

    def __init__(self, axis_name: str):
        super().__init__()
        self.axis_name = axis_name
        self._create_widgets()
        self._layout_widgets()
        self._connect_signals()

    def _create_widgets(self):
        """Create all widgets for this axis control."""
        self.position_display = QLineEdit("0.0")
        self.position_display.setReadOnly(True)
        self.position_display.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.step_spinbox = QDoubleSpinBox(
            value=1.0, singleStep=0.1, minimum=0.01, maximum=1000.0, decimals=2
        )
        self.goto_spinbox = QDoubleSpinBox(
            minimum=-100000.0, maximum=100000.0, decimals=2
        )

        self.jog_fwd_button = QPushButton("▶")
        self.jog_bwd_button = QPushButton("◀")
        self.jog_fwd_button.setAutoRepeat(False)
        self.jog_bwd_button.setAutoRepeat(False)

        self.rel_fwd_button = QPushButton("+")
        self.rel_bwd_button = QPushButton("-")
        self.goto_button = QPushButton("Go")

    def _layout_widgets(self):
        """Layout all the widgets in a grid."""
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(f"{self.axis_name}:"), 0, 0)
        layout.addWidget(self.position_display, 0, 1)
        layout.addWidget(QLabel("µm"), 0, 2)
        layout.addWidget(self.rel_bwd_button, 0, 3)
        layout.addWidget(self.step_spinbox, 0, 4)
        layout.addWidget(self.rel_fwd_button, 0, 5)
        layout.addWidget(self.jog_bwd_button, 0, 6)
        layout.addWidget(self.jog_fwd_button, 0, 7)
        layout.addWidget(self.goto_spinbox, 0, 8)
        layout.addWidget(self.goto_button, 0, 9)

    def _connect_signals(self):
        """Connect widget signals to internal handlers."""
        self.goto_button.clicked.connect(
            lambda: self.move_to_requested.emit(self.goto_spinbox.value())
        )
        self.rel_fwd_button.clicked.connect(
            lambda: self.move_by_requested.emit(self.step_spinbox.value())
        )
        self.rel_bwd_button.clicked.connect(
            lambda: self.move_by_requested.emit(-self.step_spinbox.value())
        )
        # Jog speed is 10x the relative step size
        self.jog_fwd_button.pressed.connect(
            lambda: self.jog_started.emit(self.step_spinbox.value() * 10)
        )
        self.jog_bwd_button.pressed.connect(
            lambda: self.jog_started.emit(-self.step_spinbox.value() * 10)
        )
        self.jog_fwd_button.released.connect(self.jog_stopped.emit)
        self.jog_bwd_button.released.connect(self.jog_stopped.emit)

    def set_position(self, value: float):
        """Updates the position display, formatting to 2 decimal places."""
        self.position_display.setText(f"{value:.2f}")


class NavigationPanel(QGroupBox):
    """A panel that aggregates multiple AxisControlWidgets for full navigation."""

    # --- Public Signals ---
    move_to_requested = Signal(str, float)
    move_by_requested = Signal(str, float)
    jog_started = Signal(str, float)
    jog_stopped = Signal(str)
    stop_all_requested = Signal()

    def __init__(self):
        super().__init__("Navigation")
        self.axis_widgets: dict[str, AxisControlWidget] = {}
        self._create_widgets()
        self._layout_widgets()
        self._connect_signals()

    def _create_widgets(self):
        """Create instances of AxisControlWidget for each physical axis."""
        AXES = ["XY-X", "XY-Y", "Z-Stage", "Z-Piezo", "Filter-Z", "Galvo-Y"]
        for axis_name in AXES:
            self.axis_widgets[axis_name] = AxisControlWidget(axis_name)
        self.stop_all_button = QPushButton("STOP ALL")
        self.stop_all_button.setStyleSheet("background-color: #A62929; color: white;")

    def _layout_widgets(self):
        """Layout the axis widgets and the master stop button."""
        layout = QFormLayout(self)
        for widget in self.axis_widgets.values():
            layout.addRow(widget)
        layout.addRow(self.stop_all_button)

    def _connect_signals(self):
        """Connect signals from child widgets to this panel's public signals."""
        for axis_name, widget in self.axis_widgets.items():
            widget.move_to_requested.connect(
                partial(self.move_to_requested.emit, axis_name)
            )
            widget.move_by_requested.connect(
                partial(self.move_by_requested.emit, axis_name)
            )
            widget.jog_started.connect(partial(self.jog_started.emit, axis_name))
            widget.jog_stopped.connect(partial(self.jog_stopped.emit, axis_name))
        self.stop_all_button.clicked.connect(self.stop_all_requested.emit)

    def update_positions(self, positions: dict[str, float]):
        """Public slot to update all axis displays from the engine."""
        for axis_name, position in positions.items():
            if axis_name in self.axis_widgets:
                self.axis_widgets[axis_name].set_position(position)
