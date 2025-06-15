from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    """
    The main user interface window (the View). It is responsible for
    displaying widgets and emitting signals on user interaction.
    """

    start_acquisition_requested = Signal(dict)
    cancel_acquisition_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Microscope Control")

        # --- UI Elements ---
        self.z_step_input = QLineEdit("1.0")
        self.num_slices_input = QLineEdit("150")
        self.exposure_input = QLineEdit("10.0")
        self.save_dir_input = QLineEdit("./acquisition_data")
        self.save_prefix_input = QLineEdit("ZStack")

        self.browse_button = QPushButton("Browse...")
        self.demo_mode_checkbox = QCheckBox("Run in Demo Mode")
        self.demo_mode_checkbox.setChecked(True)

        self.start_button = QPushButton("Start Z-Stack")
        self.cancel_button = QPushButton("Cancel Acquisition")

        # FIX: Replace QLabel with a read-only QTextEdit for copy-paste
        self.status_display = QTextEdit()
        self.status_display.setReadOnly(True)
        self.status_display.setMaximumHeight(80)  # Prevent it from taking too much space
        self.status_display.setText("Status: Idle. Select a config file to load.")

        # --- Layout ---
        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        form_layout = QFormLayout()

        dir_widget = QWidget()
        dir_layout = QHBoxLayout(dir_widget)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.addWidget(self.save_dir_input)
        dir_layout.addWidget(self.browse_button)

        form_layout.addRow("Z-Step (µm):", self.z_step_input)
        form_layout.addRow("Number of Slices:", self.num_slices_input)
        form_layout.addRow("Exposure (ms):", self.exposure_input)
        form_layout.addRow("Save Directory:", dir_widget)
        form_layout.addRow("Save Prefix:", self.save_prefix_input)
        form_layout.addRow(self.demo_mode_checkbox)

        layout.addLayout(form_layout)
        layout.addWidget(self.start_button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.status_display)  # Add the new QTextEdit to the layout

        self.setCentralWidget(central_widget)

        # --- Connect internal UI signals ---
        self.start_button.clicked.connect(self._on_start_clicked)
        self.cancel_button.clicked.connect(self.cancel_acquisition_requested)
        self.browse_button.clicked.connect(self._on_browse_clicked)

    def _on_start_clicked(self):
        """Gathers parameters and emits the request signal."""
        params = {
            "z_step_um": float(self.z_step_input.text()),
            "num_slices": int(self.num_slices_input.text()),
            "camera_exposure_ms": float(self.exposure_input.text()),
            "laser_duration_ms": float(self.exposure_input.text()),
            "save_dir": self.save_dir_input.text(),
            "save_prefix": self.save_prefix_input.text(),
            "should_save": True,
            "galvo_card_addr": "33",
            "galvo_axis": "A",
            "plogic_card_addr": "36",
            "plogic_axis_letter": "E",
            "microns_per_degree": 100.0,
        }
        self.start_acquisition_requested.emit(params)

    def _on_browse_clicked(self):
        """Opens a dialog to select a save directory."""
        dir = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if dir:
            self.save_dir_input.setText(dir)

    @Slot(str)
    def update_status(self, message: str):
        """Public slot for the Controller to update the status display."""
        # Use setText for QTextEdit. It will correctly handle multi-line text.
        self.status_display.setText(f"Status: {message}")

    @Slot()
    def on_acquisition_started(self):
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    @Slot()
    def on_acquisition_finished(self):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
