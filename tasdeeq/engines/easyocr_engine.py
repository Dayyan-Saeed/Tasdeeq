"""Engine B: EasyOCR with the Urdu+English models (CPU or GPU)."""
from __future__ import annotations

import numpy as np
from PIL import Image

from ..schema import OCRResult
from .base import OCREngine, order_by_y

MIN_CONF = 0.2


class EasyOCREngine(OCREngine):
    name = "easyocr"

    def __init__(self, gpu: bool | None = None) -> None:
        self._gpu = gpu
        self._reader = None

    def _load(self):
        if self._reader is None:
            import easyocr
            import torch

            gpu = torch.cuda.is_available() if self._gpu is None else self._gpu
            self._reader = easyocr.Reader(["ur", "en"], gpu=gpu, verbose=False)
        return self._reader

    def warmup(self) -> "EasyOCREngine":
        self._load()
        return self

    def read(self, image: Image.Image) -> OCRResult:
        reader = self._load()
        boxes = reader.readtext(np.array(image.convert("RGB")))
        return self._result(self.name, order_by_y(boxes, min_conf=MIN_CONF))
