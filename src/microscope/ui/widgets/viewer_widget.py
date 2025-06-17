# src/microscope/ui/widgets/viewer_widget.py
import numpy as np
from PySide6.QtCore import Slot
from qtpy.QtCore import Qt
from qtpy.QtGui import QImage, QPixmap
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget


class ViewerWidget(QWidget):
    """
    A simple widget to display acquired images.
    This widget is robust in handling various numpy image formats (8-bit, 16-bit
    grayscale, and 8-bit RGB/RGBA) and displays them efficiently.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.label = QLabel("Image Viewer")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setMinimumSize(512, 512)
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.label)
        self.setLayout(main_layout)

    @Slot(object, dict)
    def on_new_frame(self, image: np.ndarray, metadata: dict):
        """Displays a new numpy image array."""
        if not isinstance(image, np.ndarray):
            return

        try:
            height, width, *extra = image.shape
            q_format = None
            bytes_per_line = 0

            if image.ndim == 2:  # Grayscale
                if image.dtype == np.uint8:
                    q_format = QImage.Format.Format_Grayscale8
                    bytes_per_line = width
                elif image.dtype == np.uint16:
                    q_format = QImage.Format.Format_Grayscale16
                    bytes_per_line = width * 2
            elif image.ndim == 3 and extra[0] in (3, 4):  # RGB/RGBA
                if image.dtype == np.uint8:
                    q_format = QImage.Format.Format_RGB888 if extra[0] == 3 else QImage.Format.Format_RGBA8888
                    bytes_per_line = width * extra[0]

            if q_format is None:
                print(f"Warning: Unsupported image format {image.dtype}, {image.shape}")
                return

            q_image = QImage(image.data, width, height, bytes_per_line, q_format)

            # For RGB888, Qt often expects BGR, so we swap.
            if q_format == QImage.Format.Format_RGB888:
                q_image = q_image.rgbSwapped()

            pixmap = QPixmap.fromImage(q_image)
            self.label.setPixmap(
                pixmap.scaled(
                    self.label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception as e:
            print(f"Error displaying image: {e}")
