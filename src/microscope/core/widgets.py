# src/microscope/core/widgets.py

import logging

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

# Set up logger
logger = logging.getLogger(__name__)


class GalvoControlWidget(QWidget):
    """
    A widget to control the X and Y offset of a galvo scanner.

    This widget reads and writes the 'SingleAxisXOffset(deg)' and
    'SingleAxisYOffset(deg)' properties, allowing for real-time manual control
    of the galvo's 'A' (X) and 'B' (Y) axis positions.
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
        self.property_name_a = "SingleAxisXOffset(deg)"
        self.property_name_b = "SingleAxisYOffset(deg)"
        self._device_loaded = False

        # --- UI Elements ---
        # Axis A (X)
        self.pos_label_a = QLabel("Current X Offset (deg):")
        self.pos_display_a = QLineEdit("N/A")
        self.pos_display_a.setReadOnly(True)
        self.pos_display_a.setStyleSheet("background-color: #f0f0f0;")

        self.set_pos_label_a = QLabel("Set X Offset (deg):")
        self.set_pos_input_a = QDoubleSpinBox()
        self.set_pos_input_a.setRange(-5.0, 5.0)
        self.set_pos_input_a.setDecimals(3)
        self.set_pos_input_a.setSingleStep(0.1)
        self.move_button_a = QPushButton("Set X")

        # Axis B (Y)
        self.pos_label_b = QLabel("Current Y Offset (deg):")
        self.pos_display_b = QLineEdit("N/A")
        self.pos_display_b.setReadOnly(True)
        self.pos_display_b.setStyleSheet("background-color: #f0f0f0;")

        self.set_pos_label_b = QLabel("Set Y Offset (deg):")
        self.set_pos_input_b = QDoubleSpinBox()
        self.set_pos_input_b.setRange(-5.0, 5.0)
        self.set_pos_input_b.setDecimals(3)
        self.set_pos_input_b.setSingleStep(0.1)
        self.move_button_b = QPushButton("Set Y")

        # --- Layout ---
        group_box = QGroupBox(f"Galvo '{self.device_label}' Axis Control")
        grid_layout = QGridLayout()
        grid_layout.addWidget(self.pos_label_a, 0, 0)
        grid_layout.addWidget(self.pos_display_a, 0, 1)
        grid_layout.addWidget(self.set_pos_label_a, 1, 0)
        grid_layout.addWidget(self.set_pos_input_a, 1, 1)
        grid_layout.addWidget(self.move_button_a, 1, 2)

        grid_layout.addWidget(self.pos_label_b, 2, 0)
        grid_layout.addWidget(self.pos_display_b, 2, 1)
        grid_layout.addWidget(self.set_pos_label_b, 3, 0)
        grid_layout.addWidget(self.set_pos_input_b, 3, 1)
        grid_layout.addWidget(self.move_button_b, 3, 2)

        group_box.setLayout(grid_layout)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(group_box)

        # --- Connections and Timer ---
        self.move_button_a.clicked.connect(self._on_set_offset_a)
        self.move_button_b.clicked.connect(self._on_set_offset_b)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)  # Poll every 500 ms
        self._poll_timer.timeout.connect(self._update_display)

        # Defer the initial check until the event loop starts
        QTimer.singleShot(0, self._check_device_loaded)
        self._mmc.events.systemConfigurationLoaded.connect(self._check_device_loaded)

    def _check_device_loaded(self):
        """Check if the device and properties exist, then update widget state."""
        if self.device_label not in self._mmc.getLoadedDevices():
            self._device_loaded = False
        else:
            has_prop_a = self._mmc.hasProperty(self.device_label, self.property_name_a)
            has_prop_b = self._mmc.hasProperty(self.device_label, self.property_name_b)
            self._device_loaded = has_prop_a and has_prop_b

        if self._device_loaded:
            logger.info(f"Galvo '{self.device_label}' found. Enabling widget.")
            self.setEnabled(True)
            self._update_limits()
            if not self._poll_timer.isActive():
                self._poll_timer.start()
            self._update_display()
        else:
            msg = f"Galvo '{self.device_label}' and/or properties not found. Disabling widget."
            logger.warning(msg)
            self.setEnabled(False)
            self.pos_display_a.setText("Not Loaded")
            self.pos_display_b.setText("Not Loaded")
            if self._poll_timer.isActive():
                self._poll_timer.stop()

    def _update_limits(self):
        """Set spinbox limits from device properties if they exist."""

        def _update_one(prop_name, spin_box):
            try:
                lower = self._mmc.getPropertyLowerLimit(self.device_label, prop_name)
                upper = self._mmc.getPropertyUpperLimit(self.device_label, prop_name)
                spin_box.setRange(float(lower), float(upper))
            except Exception as e:
                logger.warning(f"Could not get property limits for '{prop_name}': {e}")

        _update_one(self.property_name_a, self.set_pos_input_a)
        _update_one(self.property_name_b, self.set_pos_input_b)

    def _update_display(self):
        """Update the current position display by reading from the device."""
        if not self._device_loaded:
            return

        def _update_one(prop_name, display_widget):
            try:
                pos = self._mmc.getProperty(self.device_label, prop_name)
                display_widget.setText(f"{float(pos):.3f}")
            except Exception as e:
                display_widget.setText("Error")
                logger.error(f"Error getting property '{prop_name}': {e}")
                self._check_device_loaded()  # Re-verify device state

        _update_one(self.property_name_a, self.pos_display_a)
        _update_one(self.property_name_b, self.pos_display_b)

    def _set_offset(self, prop_name: str, value: float):
        """Set a galvo offset property."""
        if not self._device_loaded:
            return
        try:
            logger.info(f"Setting {self.device_label}.{prop_name} = {value:.3f}")
            self._mmc.setProperty(self.device_label, prop_name, value)
        except Exception as e:
            logger.error(f"Failed to set property '{prop_name}': {e}")

    def _on_set_offset_a(self):
        """Handle setting the X-axis offset."""
        self._set_offset(self.property_name_a, self.set_pos_input_a.value())

    def _on_set_offset_b(self):
        """Handle setting the Y-axis offset."""
        self._set_offset(self.property_name_b, self.set_pos_input_b.value())

    def closeEvent(self, event):
        """Ensure timer is stopped on close."""
        self._poll_timer.stop()
        super().closeEvent(event)
