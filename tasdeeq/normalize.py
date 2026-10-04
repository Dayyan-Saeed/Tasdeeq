"""Text normalization shared by extraction, verification, and engine comparison.

OCR of Urdu invoices typically mixes Arabic-Indic digits, zero-width joiners,
tatweel, and Arabic punctuation. Everything must be canonicalized before any
comparison or numeric parsing happens.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Optional

# Urdu (U+06F0..06F9) and Arabic-Indic (U+0660..0669) digits -> ASCII
_DIGIT_MAP = {ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")}
_DIGIT_MAP.update({ord(a): str(i) for i, a in enumerate("٠١٢٣٤٥٦٧٨٩")})

# Characters to delete outright: tatweel, zero-width, BOM, directional marks.
_STRIP = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u200e\u200f\u061c\u0640"), None)

# OCR routinely mixes Arabic Yeh/U+064A and Alef Maksura/U+0649 into the
# Urdu Yeh U+06CC — unify before any label lookup or similarity.
# Arabic Kaf U+0643 also shows up (Qaari reads Urdu ک U+06A9 as Arabic ك).
_LETTER_MAP = {0x064A: 0x06CC, 0x0649: 0x06CC, 0x0643: 0x06A9}

_PUNCT_MAP = {
    ord("،"): ",",  # Arabic comma
    ord("؛"): ";",  # Arabic semicolon
    ord("؟"): "?",  # Arabic question mark
    ord("۔"): ".",  # Arabic full stop
    ord("٫"): ".",  # Arabic decimal separator
    ord("٬"): "",   # Arabic thousands separator
    ord("“"): '"', ord("”"): '"',
    ord("‘"): "'", ord("’"): "'",
    ord("ـ"): "",   # tatweel (also in _STRIP; harmless)
}

_WS_RE = re.compile(r"[ \t\u00a0]+")
_DATE_RE = re.compile(
    r"(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})"  # YYYY MM DD (OCR may drop hyphens)
    r"|(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4})"  # DD MM YYYY
)
_AMOUNT_TOKEN_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _letters(s: str) -> str:
    return s.translate(_LETTER_MAP)


def normalize_text(s: str) -> str:
    """Full canonicalization: unicode, digits, punctuation, whitespace."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _letters(s)
    s = s.translate(_DIGIT_MAP)
    s = s.translate(_STRIP)
    s = s.translate(_PUNCT_MAP)
    s = _WS_RE.sub(" ", s).strip()
    return s


def normalize_digits(s: str) -> str:
    """Only letter/digit/punct normalization — used for edit-distance comparisons."""
    if not s:
        return ""
    s = _letters(s)
    s = s.translate(_DIGIT_MAP)
    s = s.translate(_STRIP)
    s = s.translate(_PUNCT_MAP)
    return _WS_RE.sub(" ", s).strip()


def parse_amount(s: Optional[str]) -> Optional[float]:
    """Parse a money/quantity string into float; None if not numeric.

    Finds the first numeric token (handles currency words/symbols and
    thousands separators around it).
    """
    if s is None:
        return None
    m = _AMOUNT_TOKEN_RE.search(normalize_digits(str(s)))
    if not m:
        return None
    t = m.group(0).replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_date(s: Optional[str]) -> Optional[date]:
    """Parse DD-MM-YYYY / YYYY-MM-DD (also / and . separators) to a real date."""
    if not s:
        return None
    t = normalize_digits(s)
    m = _DATE_RE.search(t)
    if not m:
        return None
    try:
        if m.group(1):  # YYYY-MM-DD
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        # DD-MM-YYYY -> date(year, month, day)
        return date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    except ValueError:
        return None


def iso_date(s: Optional[str]) -> Optional[str]:
    d = parse_date(s)
    return d.isoformat() if d else None


def edit_distance(a: str, b: str, limit: Optional[int] = None) -> int:
    """Levenshtein distance (iterative, two-row).

    With ``limit`` set, returns ``limit + 1`` as soon as the distance is
    provably greater than the bound — callers that only compare against a
    small threshold (fuzzy label matching) skip the full O(n*m) table.
    """
    if a == b:
        return 0
    if limit is not None:
        if abs(len(a) - len(b)) > limit:
            return limit + 1
        if limit == 0:
            return 1 if a != b else 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            v = prev[j] + 1
            v2 = cur[j - 1] + 1
            if v2 < v:
                v = v2
            v3 = prev[j - 1] + (ca != cb)
            if v3 < v:
                v = v3
            cur.append(v)
            if v < row_min:
                row_min = v
        if limit is not None and row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def normalized_similarity(a: str, b: str) -> float:
    """1.0 = identical after normalization, 0.0 = completely different."""
    a, b = normalize_digits(a), normalize_digits(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return 1.0 - edit_distance(a, b) / max(len(a), len(b))
