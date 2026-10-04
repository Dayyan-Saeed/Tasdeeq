"""Engine registry. Engine A (Qaari) is optional and lazy — import guarded."""
from __future__ import annotations

from .base import OCREngine
from .easyocr_engine import EasyOCREngine
from .tesseract_engine import TesseractEngine


def get_engine(name: str, **kwargs) -> OCREngine:
    if name == "easyocr":
        return EasyOCREngine(**kwargs)
    if name == "tesseract":
        return TesseractEngine()
    if name == "qaari":
        from .qaari import QaariEngine  # lazy: heavy GPU deps

        return QaariEngine(**kwargs)
    raise ValueError(f"unknown engine {name!r} (expected easyocr|tesseract|qaari)")


__all__ = ["OCREngine", "EasyOCREngine", "TesseractEngine", "get_engine"]
