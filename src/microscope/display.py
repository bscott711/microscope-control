"""
Display Utilities

This module contains helper functions for preparing images for display in the GUI.
"""

import numpy as np


def normalize_to_8bit(image: np.ndarray) -> np.ndarray:
    """
    Normalizes a NumPy array to an 8-bit image for display.

    This function efficiently scales the image contrast to use the full 0-255
    dynamic range, avoiding excessive memory allocations.

    Args:
        image: The input image array (e.g., uint16).

    Returns:
        A contrast-stretched 8-bit (uint8) image array.
    """
    # If the image is already 8-bit, it doesn't need normalization.
    if image.dtype == np.uint8:
        return image

    min_val = image.min()
    max_val = image.max()

    if max_val > min_val:
        # Use a memory-efficient approach to scale to the 8-bit range.
        # This creates a single temporary float32 array, performs the
        # calculations in-place, and then converts to uint8.
        image_f32 = image.astype(np.float32)
        image_f32 -= min_val
        image_f32 /= max_val - min_val
        image_f32 *= 255
        return image_f32.astype(np.uint8)

    # Handle the case of a completely uniform image.
    return np.zeros_like(image, dtype=np.uint8)
