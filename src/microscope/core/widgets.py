# src/microscope/core/widgets.py

import logging
from functools import partial

from pymmcore_plus import CMMCorePlus
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class GalvoControlWidget(QWidget):
    """
    A widget to control the X and Y offset of a galvo scanner.

    This widget reads and writes the 'SingleAxisXOffset(deg)' and
    'SingleAxisYOffset(deg)' properties, allowing for real-time manual control
    of the galvo's 'A' (X) and 'B' (Y) axis positions. It updates its display
    in real-time by listening to propertyChanged events from pymmcore-plus.
    """

    def __init__(self, mmc: CMMCorePlus, device_label: str, parent=None):
        """
        Initialize the GalvoControlWidget.

        Args:
            mmc: The CMMCorePlus instance.
            device_label: The Micro-Manager label for the galvo scanner device.
            parent: The parent widget, if any.
        """
        super().__init__(parent)
        self.setWindowTitle(f"{device_label} Control")
        self._mmc = mmc
        self.device_label = device_label
        self.property_name_x = "SingleAxisXOffset(deg)"
        self.property_name_y = "SingleAxisYOffset(deg)"
        self._device_loaded = False

        # --- Main Layout ---
        group_box = QGroupBox(f"Galvo '{self.device_label}' Axis Control")
        self._grid_layout = QGridLayout()
        group_box.setLayout(self._grid_layout)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(group_box)

        # Defer device check and connect to system events
        QTimer.singleShot(0, self._check_device_loaded)
        self._mmc.events.systemConfigurationLoaded.connect(self._check_device_loaded)

    def _check_device_loaded(self):
        """Check if the device and properties exist, then update widget state."""
        # Disconnect any existing signals to prevent multiple connections
        try:
            self._mmc.events.propertyChanged.disconnect(self._on_property_changed)
        except (TypeError, RuntimeError):
            pass  # Fails if not connected, which is fine

        is_loaded = (
            self.device_label in self._mmc.getLoadedDevices()
            and self._mmc.hasProperty(self.device_label, self.property_name_x)
            and self._mmc.hasProperty(self.device_label, self.property_name_y)
        )

        self.setEnabled(is_loaded)
        if is_loaded:
            if not self._device_loaded:  # First time loading
                logger.info(f"Galvo '{self.device_label}' found. Initializing widget.")
                self._build_ui()
            self._device_loaded = True
            # Connect to property change events for real-time updates
            self._mmc.events.propertyChanged.connect(self._on_property_changed)
        else:
            logger.warning(f"Galvo '{self.device_label}' not found. Disabling widget.")
            self._device_loaded = False

    def _build_ui(self):
        """Create the UI elements for both axes."""
        # Axis X
        (
            self.x_display,
            self.x_input,
            self.x_button,
        ) = self._create_axis_group("X", self.property_name_x, row=0)

        # Axis Y
        (
            self.y_display,
            self.y_input,
            self.y_button,
        ) = self._create_axis_group("Y", self.property_name_y, row=2)

    def _create_axis_group(self, name: str, prop_name: str, row: int) -> tuple[QLineEdit, QDoubleSpinBox, QPushButton]:
        """Factory method to create the UI for a single axis."""
        # Create UI elements
        display_label = QLabel(f"Current {name} Offset (deg):")
        display_widget = QLineEdit("N/A")
        display_widget.setReadOnly(True)
        display_widget.setStyleSheet("background-color: #f0f0f0;")

        set_label = QLabel(f"Set {name} Offset (deg):")
        input_widget = QDoubleSpinBox()
        input_widget.setDecimals(3)
        input_widget.setSingleStep(0.1)

        set_button = QPushButton(f"Set {name}")

        # Add to layout
        self._grid_layout.addWidget(display_label, row, 0)
        self._grid_layout.addWidget(display_widget, row, 1)
        self._grid_layout.addWidget(set_label, row + 1, 0)
        self._grid_layout.addWidget(input_widget, row + 1, 1)
        self._grid_layout.addWidget(set_button, row + 1, 2)

        # Update limits and display with current values
        self._update_limits(prop_name, input_widget)
        self._update_display(prop_name, display_widget)

        # Connect button to a generalized handler
        set_button.clicked.connect(partial(self._set_offset, prop_name, input_widget))
        return display_widget, input_widget, set_button

    def _update_limits(self, prop_name: str, spin_box: QDoubleSpinBox):
        """Set spinbox limits from device properties."""
        try:
            lower = self._mmc.getPropertyLowerLimit(self.device_label, prop_name)
            upper = self._mmc.getPropertyUpperLimit(self.device_label, prop_name)
            spin_box.setRange(float(lower), float(upper))
        except Exception as e:
            logger.warning(f"Could not get property limits for '{prop_name}': {e}")

    def _update_display(self, prop_name: str, display_widget: QLineEdit):
        """Update a display widget with the current property value."""
        try:
            pos = self._mmc.getProperty(self.device_label, prop_name)
            display_widget.setText(f"{float(pos):.3f}")
        except Exception as e:
            display_widget.setText("Error")
            logger.error(f"Error getting property '{prop_name}': {e}")
            # Re-verify device state if communication fails
            self._check_device_loaded()

    def _set_offset(self, prop_name: str, input_widget: QDoubleSpinBox):
        """Set a galvo offset property based on the input widget's value."""
        try:
            value = input_widget.value()
            logger.info(f"Setting {self.device_label}.{prop_name} = {value:.3f}")
            self._mmc.setProperty(self.device_label, prop_name, value)
        except Exception as e:
            logger.error(f"Failed to set property '{prop_name}': {e}")

    def _on_property_changed(self, device: str, prop: str, value: str):
        """Listen for property changes and update the UI if relevant."""
        if device != self.device_label:
            return

        if prop == self.property_name_x:
            self.x_display.setText(f"{float(value):.3f}")
        elif prop == self.property_name_y:
            self.y_display.setText(f"{float(value):.3f}")

    def closeEvent(self, event):
        """Ensure signals are disconnected when the widget is closed."""
        try:
            self._mmc.events.propertyChanged.disconnect(self._on_property_changed)
        except (TypeError, RuntimeError):
            pass
        super().closeEvent(event)
