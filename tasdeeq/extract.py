"""Rule/regex field extraction from OCR text.

Designed for printed Urdu invoices with bilingual labels (the synthetic
generator emits the same label vocabulary). Label-based lookup only — no
aggressive guessing: a missing field yields None so the verifier can flag it.
"""
from __future__ import annotations

import re
from typing import Optional

from .normalize import edit_distance, iso_date, normalize_text, parse_amount
from .schema import Invoice, LineItem, OCRResult

INVOICE_NUMBER_LABELS = [
    "انوائس نمبر", "بل نمبر", "شمارہ بل", "شمارہ", "انوائس",
    "Invoice No", "Invoice #", "Inv No", "Bill No",
]
DATE_LABELS = ["تاریخ", "Date"]
SUBTOTAL_LABELS = [
    "مجموعی رقم", "مجموعہ رقم", "ذیلی میزان", "ذیلی کل",
    "Sub Total", "Subtotal", "Sub-Total",
]
TAX_LABELS = [
    "وی اے ٹیکس", "سیلز ٹیکس", "مالیات", "ٹیکس",
    "Sales Tax", "VAT", "GST", "Tax",
]
TOTAL_LABELS = [
    "قابل ادائیگی", "کل رقم", "جمع کل", "میزان کل", "میزان",
    "Grand Total", "Total Amount", "Amount Payable", "Total",
]

# Table header of the rows block — never a row description (engines such as
# Qaari sometimes read rows as separate number/description lines, and the
# header line sits next to the first row).
TABLE_HEADER_LABELS = ["تفصیل تعداد شرح رقم", "تفصیل تعداد"]

# number tokens (comma-grouped, optional decimal)
_AMOUNT_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_DATE_TOKEN_RE = re.compile(
    r"\d{4}[-/. ]\d{1,2}[-/. ]\d{1,2}|\d{1,2}[-/. ]\d{1,2}[-/. ]\d{4}"
)


def _inv_fallback(lines: list[str]) -> Optional[str]:
    """Shape-based recovery when the invoice label itself is garbled.

    Collapses the line to A-Z0-9 and looks for INVddddd dddd; the year
    position is inferred so RTL-digit-order flips still form a valid shape.
    """
    for ln in lines:
        compact = re.sub(r"[^A-Z0-9]", "", ln.upper())
        m = re.search(r"INV(\d{4})(\d{4})", compact)
        if m:
            p1, p2 = m.group(1), m.group(2)
            if 2020 <= int(p1) <= 2035:
                year, other = p1, p2
            elif 2020 <= int(p2) <= 2035:
                year, other = p2, p1
            else:
                year, other = p1, p2
            return f"INV-{year}-{other}"
    return None


def _strip_label(line: str, label: str, fuzzy: bool = False) -> Optional[str]:
    """If label occurs in line, return the line WITHOUT the label.

    Search is direction-agnostic: the value may sit before or after the
    label (engines read RTL/LTR differently). None means 'label absent'.
    With fuzzy=True, OCR variants of the label (edit distance <= 2) also
    match — e.g. Qaari reads "مجموعی رقم" as "مجمووع رقم".
    """
    idx = line.find(label)
    if idx >= 0:
        rest = line[:idx] + line[idx + len(label):]
        return rest.strip(" \t:،–=-.").strip()
    if not fuzzy or len(label) < 5:
        return None
    max_dist = 1 if len(label) <= 8 else 2
    n, m = len(line), len(label)
    best: Optional[tuple[int, int, int]] = None  # (dist, start, width)
    for w in range(m - max_dist, m + max_dist + 1):
        if w < 1:
            continue
        for s in range(n - w + 1):
            d = edit_distance(line[s:s + w], label, limit=max_dist)
            if d <= max_dist and (best is None or d < best[0]):
                best = (d, s, w)
                if d == 0:
                    break
        if best and best[0] == 0:
            break
    if best is None:
        return None
    _, s, w = best
    rest = line[:s] + line[s + w:]
    return rest.strip(" \t:،–=-.").strip()


def _split_long_line(ln: str) -> list[str]:
    """Split a degenerate mega-line (Qaari can emit an entire page as one
    line) at label / date / invoice anchors so value lookups stay local.

    Short lines — the normal case for EasyOCR/Tesseract — pass through
    untouched. Cutting BEFORE each anchor keeps every label glued to its
    own value, which is what `_first_amount` assumes.
    """
    if len(ln) <= 160:
        return [ln]
    anchors = (
        INVOICE_NUMBER_LABELS
        + DATE_LABELS
        + SUBTOTAL_LABELS
        + TAX_LABELS
        + TOTAL_LABELS
        + TABLE_HEADER_LABELS
    )
    cuts: set[int] = {0}
    for anchor in anchors:
        start = 0
        while True:
            i = ln.find(anchor, start)
            if i < 0:
                break
            if i > 0:
                cuts.add(i)
            start = i + len(anchor)
    for m in _DATE_TOKEN_RE.finditer(ln):
        if m.start() > 0:
            cuts.add(m.start())
    for m in re.finditer(r"INV[-\s]?\d{4}", ln, flags=re.IGNORECASE):
        if m.start() > 0:
            cuts.add(m.start())
    pts = sorted(cuts) + [len(ln)]
    return [ln[a:b].strip() for a, b in zip(pts, pts[1:]) if ln[a:b].strip()]


def _first_amount(rest: Optional[str]) -> Optional[str]:
    if not rest:
        return None
    m = _AMOUNT_TOKEN_RE.search(rest)
    return m.group(0) if m else None


def _lookup_amount(lines: list[str], labels: list[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (value, reason) — value from label on same line, else next line.

    Exact label matches win globally; fuzzy (OCR-variant) matches only run
    when no exact label occurs anywhere.
    """
    for fuzzy in (False, True):
        for i, ln in enumerate(lines):
            for lab in labels:
                rest = _strip_label(ln, lab, fuzzy=fuzzy)
                if rest is None:
                    continue
                tok = _first_amount(rest)
                if tok:
                    return tok, f"matched label '{lab}'" + (" (fuzzy)" if fuzzy else "")
                if i + 1 < len(lines):
                    tok = _first_amount(lines[i + 1])
                    if tok:
                        return tok, f"matched label '{lab}' (next line)" + (" (fuzzy)" if fuzzy else "")
    return None, None


def _lookup_token(lines: list[str], labels: list[str], pattern: re.Pattern[str]) -> tuple[Optional[str], Optional[str]]:
    """Return first token matching pattern after one of the labels."""
    for fuzzy in (False, True):
        for i, ln in enumerate(lines):
            for lab in labels:
                rest = _strip_label(ln, lab, fuzzy=fuzzy)
                if rest is None:
                    continue  # label not present in this line — do not look ahead
                m = pattern.search(rest)
                if m:
                    return m.group(0), f"matched label '{lab}'" + (" (fuzzy)" if fuzzy else "")
                if i + 1 < len(lines):  # label found but value is on the next line
                    m = pattern.search(lines[i + 1])
                    if m:
                        return m.group(0), f"matched label '{lab}' (next line)" + (" (fuzzy)" if fuzzy else "")
    return None, None


def _desc_candidate(ln: str) -> bool:
    """A line usable as a row description pulled from a neighbouring line."""
    if not ln or _AMOUNT_TOKEN_RE.search(ln):
        return False
    if not any(c.isalpha() for c in ln):
        return False
    blocked = TOTAL_LABELS + SUBTOTAL_LABELS + TAX_LABELS + DATE_LABELS + TABLE_HEADER_LABELS
    return not any(lab in ln for lab in blocked)


def extract_line_items(lines: list[str]) -> list[LineItem]:
    """Rows with exactly three numbers + a description; direction-agnostic.

    Engines may emit desc-first (forward) or amount-first (reversed) token
    order. Columns are assigned by the qty*rate=amount invariant when OCR
    kept the digits intact, else by which side the description sits on.
    Engines like Qaari sometimes split a row into a numbers line and a
    description line — pair those with the next (then previous) line.
    """
    items: list[LineItem] = []
    for i, ln in enumerate(lines):
        ln = ln.strip()
        if any(lab in ln for lab in TOTAL_LABELS + SUBTOTAL_LABELS + TAX_LABELS + DATE_LABELS):
            continue
        if _DATE_TOKEN_RE.search(ln):  # date rows would otherwise look like 3 numbers
            continue
        nums = list(_AMOUNT_TOKEN_RE.finditer(ln))
        if len(nums) != 3:
            continue
        pieces: list[str] = []
        last = 0
        for m in nums:
            pieces.append(ln[last:m.start()])
            last = m.end()
        pieces.append(ln[last:])  # description may sit after the last number
        desc = "".join(pieces).strip(" -–:،")
        if not desc:
            # split row: take the description from the adjacent line
            for j in (i + 1, i - 1):
                if 0 <= j < len(lines) and _desc_candidate(lines[j].strip()):
                    desc = lines[j].strip()
                    break
        if not desc:
            continue

        a, b, c = (parse_amount(m.group(0)) for m in nums)

        def close(x, y) -> bool:
            return x is not None and y is not None and round(x, 2) == round(y, 2)

        if a is not None and b is not None and close(a * b, c):
            qty, rate, amount = a, b, c
        elif a is not None and c is not None and close(a * c, b):
            qty, rate, amount = a, c, b
        elif b is not None and c is not None and close(b * c, a):
            qty, rate, amount = c, b, a
        elif not ln[: nums[0].start()].strip():  # numbers lead → reversed row
            qty, rate, amount = c, b, a
        else:  # desc leads → forward row (qty rate amount)
            qty, rate, amount = a, b, c

        items.append(
            LineItem(
                description=desc,
                quantity=qty,
                unit_price=rate,
                line_total=amount,
            )
        )
    return items


def extract_invoice(ocr: OCRResult) -> tuple[Invoice, dict[str, str]]:
    """Extract fields from one engine's OCR output.

    Returns (Invoice, raw) where raw maps field -> the raw string found,
    for display and debug reasons in the verification layer.
    """
    lines = [
        seg
        for ln in ocr.lines
        for seg in _split_long_line(normalize_text(ln))
    ]
    lines = [ln for ln in lines if ln]
    raw: dict[str, str] = {}

    inv_no, _ = _lookup_token(lines, INVOICE_NUMBER_LABELS, re.compile(r"\S+"))
    if not inv_no:
        inv_no = _inv_fallback(lines)
    if inv_no:
        raw["invoice_number"] = inv_no

    date_val, _ = _lookup_token(lines, DATE_LABELS, _DATE_TOKEN_RE)
    if not date_val:  # fallback: any VALID date-shaped token anywhere (rows can
        for ln in lines:  # look like 4-2-2 numbers, so require a real calendar date)
            m = _DATE_TOKEN_RE.search(ln)
            if m and iso_date(m.group(0)):
                date_val = m.group(0)
                break
    if date_val:
        raw["date"] = date_val
        iso = iso_date(date_val)
        if iso:
            raw["date"] = iso

    subtotal, _ = _lookup_amount(lines, SUBTOTAL_LABELS)
    if subtotal:
        raw["subtotal"] = subtotal
    tax, _ = _lookup_amount(lines, TAX_LABELS)
    if tax:
        raw["tax"] = tax
    total, _ = _lookup_amount(lines, TOTAL_LABELS)
    if total:
        raw["total"] = total

    items = extract_line_items(lines)
    for i, it in enumerate(items):
        if it.quantity is not None:
            raw[f"line_items[{i}].quantity"] = str(it.quantity)
        if it.unit_price is not None:
            raw[f"line_items[{i}].unit_price"] = str(it.unit_price)
        if it.line_total is not None:
            raw[f"line_items[{i}].line_total"] = str(it.line_total)

    invoice = Invoice(
        invoice_number=inv_no,
        date=(iso_date(date_val) or date_val) if date_val else None,
        line_items=items,
        subtotal=parse_amount(subtotal),
        tax=parse_amount(tax),
        total=parse_amount(total),
    )
    return invoice, raw
