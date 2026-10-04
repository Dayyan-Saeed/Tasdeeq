"""Data models for Tasdeeq. Stdlib dataclasses only — no external deps."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

STATUS_GREEN = "green"
STATUS_AMBER = "amber"
STATUS_RED = "red"


@dataclass
class LineItem:
    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None


@dataclass
class Invoice:
    """Structured fields extracted from a single OCR reading."""

    invoice_number: Optional[str] = None
    date: Optional[str] = None  # ISO YYYY-MM-DD after parsing; raw otherwise
    line_items: list[LineItem] = field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Invoice":
        items = [LineItem(**it) for it in d.get("line_items", [])]
        return cls(
            invoice_number=d.get("invoice_number"),
            date=d.get("date"),
            line_items=items,
            subtotal=d.get("subtotal"),
            tax=d.get("tax"),
            total=d.get("total"),
        )


@dataclass
class OCRResult:
    """Raw output of one OCR engine."""

    engine: str
    text: str
    lines: list[str] = field(default_factory=list)

    @classmethod
    def from_text(cls, engine: str, text: str) -> "OCRResult":
        return cls(engine=engine, text=text, lines=[ln for ln in text.splitlines() if ln.strip()])


@dataclass
class FieldVerdict:
    """Verification verdict for one field."""

    field: str  # e.g. "total", "line_items[0].line_total"
    value: Any  # the agreed/candidate value shown to the reviewer
    status: str  # green | amber | red
    confidence: float  # 0..1
    reasons: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)  # error-localization suggestions, never auto-applied

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    invoice: Invoice  # merged/agreed invoice (best guess per field)
    verdicts: list[FieldVerdict] = field(default_factory=list)

    def verdict_map(self) -> dict[str, FieldVerdict]:
        return {v.field: v for v in self.verdicts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice": self.invoice.to_dict(),
            "verdicts": [v.to_dict() for v in self.verdicts],
        }
