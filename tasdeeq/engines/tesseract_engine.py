"""Engine B-2 / fallback: Tesseract with bundled Urdu+English tessdata."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from PIL import Image

from ..schema import OCRResult
from .base import OCREngine

TESSDATA_DIR = Path(__file__).parent / "tessdata"
_COMMON_INSTALLS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
]


def _tesseract_cmd() -> str | None:
    found = shutil.which("tesseract")
    if found:
        return found
    for p in _COMMON_INSTALLS:
        if Path(p).exists():
            return p
    return None


class TesseractEngine(OCREngine):
    name = "tesseract"

    def __init__(self) -> None:
        self._cmd = _tesseract_cmd()
        self._langs = "+".join(
            p.stem for p in sorted(TESSDATA_DIR.glob("*.traineddata"))
        ) or "urd+eng"

    @property
    def available(self) -> bool:
        return self._cmd is not None

    def read(self, image: Image.Image) -> OCRResult:
        import pytesseract

        if not self._cmd:
            raise RuntimeError(
                "tesseract executable not found — install UB-Mannheim.TesseractOCR "
                "or run on Colab (apt install tesseract-ocr tesseract-ocr-urd)"
            )
        pytesseract.pytesseract.tesseract_cmd = self._cmd
        if TESSDATA_DIR.exists():
            os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)
        text = pytesseract.image_to_string(image, lang=self._langs)
        return self._result(self.name, text.splitlines())
