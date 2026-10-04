"""OCR engine interface: every engine reads an image -> OCRResult."""
from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image

from ..schema import OCRResult


class OCREngine(ABC):
    """One OCR backend. Implementations lazy-load models on first read()."""

    name: str = "base"

    @abstractmethod
    def read(self, image: Image.Image) -> OCRResult:
        """OCR a (preprocessed) image into text lines, top to bottom."""

    def warmup(self) -> "OCREngine":
        """Load weights now instead of on first read() (ZeroGPU wants
        module-scope loading; overridden by engines that lazy-load)."""
        return self

    @staticmethod
    def _result(engine: str, lines: list[str]) -> OCRResult:
        lines = [ln.strip() for ln in lines if ln and ln.strip()]
        return OCRResult(engine=engine, text="\n".join(lines), lines=lines)


def order_by_y(boxes: list[tuple[list, str, float]], min_conf: float = 0.0) -> list[str]:
    """Turn EasyOCR-style (bbox, text, conf) into visual lines.

    Boxes are clustered into rows by vertical center (word boxes from one
    line must be merged back together), rows sorted top-to-bottom, boxes
    within a row sorted left-to-right (synthetic lines are logical LTR).
    """
    kept = [
        (min(p[0] for p in b), min(p[1] for p in b), max(p[0] for p in b), max(p[1] for p in b), t.strip())
        for b, t, c in boxes
        if c >= min_conf and t and t.strip()
    ]
    if not kept:
        return []
    kept.sort(key=lambda k: (k[1] + k[3]))  # by vertical center

    rows: list[list[tuple]] = []
    for box in kept:
        cy = (box[1] + box[3]) / 2
        h = max(box[3] - box[1], 1)
        if rows:
            prev = rows[-1]
            prev_cy = sum((b[1] + b[3]) / 2 for b in prev) / len(prev)
            prev_h = sum(max(b[3] - b[1], 1) for b in prev) / len(prev)
            if abs(cy - prev_cy) < 0.6 * max(h, prev_h):
                prev.append(box)
                continue
        rows.append([box])

    lines = []
    for row in rows:
        row.sort(key=lambda b: b[0])  # left to right
        lines.append("  ".join(b[4] for b in row))
    return lines
