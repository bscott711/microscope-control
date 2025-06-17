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
        # Set a minimum size to ensure the label is visible even without an image
        self.label.setMinimumSize(512, 512)

        # Create the main layout manager for the widget
        main_layout = QVBoxLayout()
        # Add the image display label to the layout
        main_layout.addWidget(self.label)
        # Set the fully configured layout for the parent widget
        self.setLayout(main_layout)

    @Slot(object, dict)
    def on_new_frame(self, image: np.ndarray, metadata: dict):
        """
        Displays a new numpy image array.
        This method supports 8-bit grayscale (uint8, 2D), 16-bit grayscale (uint16, 2D),
        and 8-bit color images (uint8, 3D with 3 or 4 channels - RGB/RGBA).
        """
        if image is None:
            # If no image data is provided, clear the label and return
            self.label.clear()
            return

        # Ensure image has at least 2 dimensions (height, width)
        if image.ndim < 2:
            print(f"Warning: Image has too few dimensions ({image.ndim}). Expected 2 or 3.")
            return

        height, width = image.shape[0], image.shape[1]
        q_format: QImage.Format | None = None
        bytes_per_line: int | None = None

        try:
            # Determine QImage format and bytes_per_line based on image properties
            if image.ndim == 2:  # Grayscale image
                if image.dtype == np.uint8:
                    q_format = QImage.Format.Format_Grayscale8
                    bytes_per_line = width
                elif image.dtype == np.uint16:
                    q_format = QImage.Format.Format_Grayscale16
                    bytes_per_line = width * 2  # 2 bytes per pixel for uint16
                else:
                    print(f"Warning: Unsupported grayscale image dtype: {image.dtype}")
                    return
            elif image.ndim == 3:  # Color image (e.g., RGB, RGBA)
                if image.dtype == np.uint8:
                    if image.shape[2] == 3:  # RGB image
                        q_format = QImage.Format.Format_RGB888
                        bytes_per_line = width * 3
                    elif image.shape[2] == 4:  # RGBA image
                        # Qt's ARGB32 is often used for RGBA, as it's common for transparency
                        q_format = QImage.Format.Format_ARGB32
                        bytes_per_line = width * 4
                    else:
                        print(f"Warning: Unsupported color image channel count: {image.shape[2]}. Expected 3 or 4.")
                        return
                else:
                    print(f"Warning: Unsupported color image dtype: {image.dtype}")
                    return
            else:
                print(f"Warning: Unsupported image dimensions: {image.ndim}.")
                return

            # Check if format was successfully determined
            if q_format is None or bytes_per_line is None:
                print("Error: Could not determine QImage format from numpy array.")
                return

            # Create a QImage from the numpy array's data buffer
            q_image = QImage(
                image.data,
                width,
                height,
                bytes_per_line,
                q_format,
            )

            # For RGB888, Qt often expects BGR byte order if numpy provides RGB.
            # rgbSwapped() can fix this if colors appear incorrect.
            if q_format == QImage.Format.Format_RGB888:
                q_image = q_image.rgbSwapped()

            # Convert the QImage to QPixmap for display
            pixmap = QPixmap.fromImage(q_image)

            # Scale the pixmap to fit the label, maintaining aspect ratio,
            # and use SmoothTransformation for better visual quality.
            self.label.setPixmap(
                pixmap.scaled(
                    self.label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ),
            )
        except Exception as e:
            print(f"Error displaying image: {e}")
