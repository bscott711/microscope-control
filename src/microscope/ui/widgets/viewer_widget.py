import numpy as np
from qtpy.QtCore import Qt, Slot
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget


class ViewerWidget(QWidget):
    """A simple widget to display acquired images."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("Image Viewer")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(512, 512)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.label)

    @Slot(object, dict)
    def on_new_frame(self, image: np.ndarray, metadata: dict):
        """Displays a new numpy image array."""
        if image is None:
            return
        height, width = image.shape
        bytes_per_line = width
        # Create a QImage from the numpy array
        q_image = QImage(image.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8)
        pixmap = QPixmap.fromImage(q_image)
        self.label.setPixmap(
            pixmap.scaled(
                self.label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation
            )
        )
