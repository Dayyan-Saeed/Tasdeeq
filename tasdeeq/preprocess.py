"""Image preprocessing: grayscale, deskew, upscale (CPU, OpenCV)."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MIN_LONG_SIDE = 1400
MAX_SKEW_DEG = 10.0


def preprocess(image: Image.Image) -> Image.Image:
    """Return a grayscale-based RGB image, deskewed and upscaled if small."""
    arr = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)

    h, w = arr.shape
    if max(h, w) < MIN_LONG_SIDE:
        scale = MIN_LONG_SIDE / max(h, w)
        arr = cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    angle = _estimate_skew(arr)
    if angle is not None:
        h, w = arr.shape
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        arr = cv2.warpAffine(arr, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    return Image.fromarray(cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB))


def _estimate_skew(arr: np.ndarray) -> float | None:
    """Skew angle via min-area rectangle over the text mask; None if unreliable."""
    _, binary = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None or len(coords) < 50:
        return None
    angle = float(cv2.minAreaRect(coords)[-1])
    # cv2 convention: angle in [-90, 0); map to small rotation in degrees
    if angle < -45:
        angle = -(90.0 + angle)
    else:
        angle = -angle
    if abs(angle) > MAX_SKEW_DEG or abs(angle) < 0.3:
        return None
    return angle
