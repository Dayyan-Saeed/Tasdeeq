"""Verification layer: the actual product edge.

Combines two engines' extractions and produces per-field
(status green/amber/red, confidence, reasons, hints).

Checks implemented (per spec §6):
  1. Arithmetic      — quantity*unit_price==line_total, sum==subtotal, subtotal+tax==total
                       (compared at cent precision — exact for currency)
  2. Engine agreement — exact match on numbers, normalized edit-distance on text
  3. Format validity — dates parse, amounts non-negative, invoice-number shape
  4. Error localization — single-digit substitution with common OCR confusions
                       to suggest which field is wrong (hint only, never auto-fix)
  5. Policy          — green only if everything passes and engines agree

The verdict for a field is the worst outcome among all applicable checks.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .normalize import normalized_similarity, parse_date
from .schema import (
    STATUS_AMBER,
    STATUS_GREEN,
    STATUS_RED,
    FieldVerdict,
    Invoice,
    LineItem,
    VerificationResult,
)

_RANK = {STATUS_GREEN: 0, STATUS_AMBER: 1, STATUS_RED: 2}
_BASE_CONF = {STATUS_GREEN: 0.9, STATUS_AMBER: 0.5, STATUS_RED: 0.25}
_REQUIRED_FIELDS = ("invoice_number", "date", "total")
_OPTIONAL_FIELDS = ("subtotal", "tax")
_SCALAR_FIELDS = ("invoice_number", "date", "subtotal", "tax", "total")
_NUM_FIELDS = {"subtotal", "tax", "total"}
_TEXT_SIM_THRESHOLD = 0.8
_INVOICE_NO_RE = re.compile(r"\S{2,30}")

# Common OCR digit confusions (symmetric pairs)
_CONFUSION_PAIRS = [
    ("0", "6"), ("0", "8"), ("0", "9"), ("1", "0"), ("1", "7"), ("1", "4"),
    ("2", "7"), ("2", "1"), ("3", "8"), ("3", "5"), ("4", "9"), ("5", "6"),
    ("5", "8"), ("6", "8"), ("7", "2"), ("8", "9"),
]
_CONFUSIONS: dict[str, tuple[str, ...]] = {}
for _a, _b in _CONFUSION_PAIRS:
    _CONFUSIONS.setdefault(_a, set()).add(_b)  # type: ignore[assignment]
    _CONFUSIONS.setdefault(_b, set()).add(_a)  # type: ignore[assignment]
_CONFUSIONS = {k: tuple(sorted(v)) for k, v in _CONFUSIONS.items()}  # type: ignore[misc]


def _money_eq(x: float, y: float) -> bool:
    return round(x, 2) == round(y, 2)


def _new_entry(value: Any) -> dict[str, Any]:
    return {"value": value, "status": STATUS_GREEN, "conf": _BASE_CONF[STATUS_GREEN], "reasons": [], "hints": []}


def _escalate(entry: dict[str, Any], status: str, reason: Optional[str] = None) -> None:
    if _RANK[status] > _RANK[entry["status"]]:
        entry["status"] = status
        entry["conf"] = min(entry["conf"], _BASE_CONF[status])
    if reason and reason not in entry["reasons"]:
        entry["reasons"].append(reason)


def _localize(
    field_values: dict[str, float],
    check: Callable[[dict[str, float]], bool],
    limit: int = 3,
) -> list[str]:
    """Try single-digit substitutions; return hints for ones that close the gap."""
    hints: list[str] = []
    for name, val in field_values.items():
        s = f"{val:.2f}"
        for pos, ch in enumerate(s):
            if not ch.isdigit() or len(hints) >= limit:
                continue
            for alt in _CONFUSIONS.get(ch, ()):
                new_val = float(s[:pos] + alt + s[pos + 1:])
                cand = dict(field_values)
                cand[name] = new_val
                try:
                    if check(cand) and new_val != val:
                        hints.append(
                            f"possible OCR misread — {name}: {val:g} → {new_val:g} would balance it"
                        )
                        break
                except (KeyError, TypeError, ValueError):
                    continue
    return hints


def _record_violation(
    reg: dict[str, dict[str, Any]],
    field_values: dict[str, float],
    check: Callable[[dict[str, float]], bool],
    desc: str,
) -> None:
    """Mark all involved fields amber, localize the likely culprit, add hints."""
    for name in field_values:
        if name in reg:
            _escalate(reg[name], STATUS_AMBER, desc)
    hints = _localize(field_values, check)
    if not hints:
        return
    fixed_fields = {h.split(":")[0].replace("possible OCR misread — ", "") for h in hints}
    for name in field_values:
        if name in reg:
            for h in hints:
                if h not in reg[name]["hints"]:
                    reg[name]["hints"].append(h)
    if len(fixed_fields) == 1:
        culprit = next(iter(fixed_fields))
        if culprit in reg:
            _escalate(
                reg[culprit],
                STATUS_RED,
                f"arithmetic does not close; a single-digit correction in {culprit} fixes it (see hint)",
            )


def _check_arithmetic(inv: Invoice, reg: dict[str, dict[str, Any]]) -> None:
    # 1. per-line: quantity * unit_price == line_total
    for i, it in enumerate(inv.line_items):
        fields = {
            f"line_items[{i}].quantity": it.quantity,
            f"line_items[{i}].unit_price": it.unit_price,
            f"line_items[{i}].line_total": it.line_total,
        }
        present = {k: v for k, v in fields.items() if v is not None}
        missing = [k.rsplit(".", 1)[1] for k, v in fields.items() if v is None]
        if missing and present:
            for k in present:
                _escalate(reg[k], STATUS_AMBER, f"line {i}: missing {', '.join(missing)} — arithmetic unverified")
        elif len(present) == 3:
            if not _money_eq(round(it.quantity * it.unit_price, 2), round(it.line_total, 2)):  # type: ignore[arg-type]
                _record_violation(
                    reg,
                    present,
                    lambda v: _money_eq(
                        round(v[f"line_items[{i}].quantity"] * v[f"line_items[{i}].unit_price"], 2),
                        round(v[f"line_items[{i}].line_total"], 2),
                    ),
                    f"line {i}: quantity × unit_price ≠ line_total",
                )

    # 2. sum(line_totals) == subtotal
    totals = {
        f"line_items[{i}].line_total": it.line_total
        for i, it in enumerate(inv.line_items)
        if it.line_total is not None
    }
    if totals:
        s = round(sum(totals.values()), 2)  # type: ignore[arg-type]
        if inv.subtotal is not None:
            if not _money_eq(s, inv.subtotal):
                vals = dict(totals)
                vals["subtotal"] = inv.subtotal
                _record_violation(
                    reg,
                    vals,
                    lambda v: _money_eq(
                        round(sum(v[k] for k in totals), 2), v["subtotal"]
                    ),
                    f"sum of line totals ({s:g}) ≠ subtotal ({inv.subtotal:g})",
                )
        else:
            _escalate(reg["subtotal"], STATUS_AMBER, f"subtotal not found; sum of line totals = {s:g}")

    # 3. subtotal + tax == total  (tax treated as 0 when absent)
    if inv.total is not None and inv.subtotal is not None:
        tax_v = inv.tax if inv.tax is not None else 0.0
        if not _money_eq(round(inv.subtotal + tax_v, 2), inv.total):
            vals: dict[str, float] = {"subtotal": inv.subtotal, "total": inv.total}
            note = ""
            if inv.tax is None:
                note = " (tax not found — assumed 0)"
            _record_violation(
                reg,
                vals,
                lambda v: _money_eq(round(v["subtotal"] + (v.get("tax", 0.0)), 2), v["total"]),
                f"subtotal + tax ≠ total{note}",
            )
    elif inv.total is not None and inv.subtotal is None and totals:
        tax_v = inv.tax if inv.tax is not None else 0.0
        s = round(sum(totals.values()), 2)  # type: ignore[arg-type]
        if not _money_eq(round(s + tax_v, 2), inv.total):
            _escalate(reg["total"], STATUS_AMBER, "subtotal missing and line totals + tax ≠ total")


def _agreement_reason(name: str, va: Any, vb: Any, is_num: bool) -> tuple[str, str]:
    """Return (status, reason) for a field present in both engines."""
    if is_num and _money_eq(float(va), float(vb)):
        return STATUS_GREEN, f"{name}: engines agree ({va:g})"
    if not is_num:
        if str(va) == str(vb):
            return STATUS_GREEN, f"{name}: engines agree ({va})"
        sim = normalized_similarity(str(va), str(vb))
        return STATUS_AMBER, f"{name}: engines differ (similarity {sim:.2f}) — A={va!r}, B={vb!r}"
    return STATUS_AMBER, f"{name}: engines disagree — A={va:g}, B={vb:g}"


def verify(a: Invoice, b: Optional[Invoice] = None) -> VerificationResult:
    """Produce per-field verdicts from one engine (b=None) or two engines."""
    single = b is None
    reg: dict[str, dict[str, Any]] = {}

    # ---- merge scalars + agreement ----
    merged = Invoice()
    for f in _SCALAR_FIELDS:
        va, vb = getattr(a, f), getattr(b, f) if b else None
        val = va if va is not None else vb
        setattr(merged, f, val)
        reg[f] = _new_entry(val)
        is_num = f in _NUM_FIELDS
        if val is None:
            if f in _REQUIRED_FIELDS:
                _escalate(reg[f], STATUS_RED, f"{f}: not found by either engine")
                reg[f]["conf"] = 0.1
            else:
                # optional (subtotal/tax): absent in both engines is NOT green on
                # its own — arithmetic must confirm it later (spec §6: a missed
                # error is worse than an extra flag).
                _escalate(
                    reg[f],
                    STATUS_AMBER,
                    f"{f}: not found in either engine — arithmetic must confirm it is truly absent",
                )
        elif not single and vb is None:
            _escalate(reg[f], STATUS_AMBER, f"{f}: found by engine A only")
        elif not single and va is None:
            _escalate(reg[f], STATUS_AMBER, f"{f}: found by engine B only")
        elif not single:
            status, reason = _agreement_reason(f, va, vb, is_num)
            _escalate(reg[f], status, reason)

    # ---- merge line items + row-level agreement ----
    if b is not None and len(a.line_items) != len(b.line_items):
        merged.line_items = a.line_items if len(a.line_items) > len(b.line_items) else b.line_items
        group_red_reason = (
            f"line_items: engines disagree on row count (A={len(a.line_items)}, B={len(b.line_items)})"
        )
    else:
        merged.line_items = list(a.line_items)
        group_red_reason = None

    for i, it in enumerate(merged.line_items):
        for part in ("description", "quantity", "unit_price", "line_total"):
            key = f"line_items[{i}].{part}"
            reg[key] = _new_entry(getattr(it, part))
        if single:
            continue
        other = b.line_items[i] if b is not None and i < len(b.line_items) else None
        if other is None:
            for part in ("description", "quantity", "unit_price", "line_total"):
                _escalate(reg[f"line_items[{i}].{part}"], STATUS_AMBER, f"line {i}: not read by engine B")
            continue
        status, reason = _agreement_reason(f"line {i} description", it.description, other.description, False)
        _escalate(reg[f"line_items[{i}].description"], status, reason)
        for part in ("quantity", "unit_price", "line_total"):
            va, vb = getattr(it, part), getattr(other, part)
            key = f"line_items[{i}].{part}"
            if va is None and vb is None:
                _escalate(reg[key], STATUS_AMBER, f"line {i}: {part} not found by either engine")
            elif va is None or vb is None:
                which = "engine A" if va is not None else "engine B"
                _escalate(reg[key], STATUS_AMBER, f"line {i} {part}: found by {which} only")
            else:
                status, reason = _agreement_reason(f"line {i} {part}", va, vb, True)
                _escalate(reg[key], status, reason)

    # ---- format validity ----
    if merged.date is not None and parse_date(str(merged.date)) is None:
        _escalate(reg["date"], STATUS_RED, f"date does not parse to a real date: {merged.date!r}")
        reg["date"]["conf"] = 0.1
    for f in _SCALAR_FIELDS:
        if f in _NUM_FIELDS and reg[f]["value"] is not None and float(reg[f]["value"]) < 0:
            _escalate(reg[f], STATUS_RED, f"{f}: negative amount ({reg[f]['value']:g})")
            reg[f]["conf"] = 0.1
    if merged.invoice_number is not None and not _INVOICE_NO_RE.fullmatch(str(merged.invoice_number)):
        _escalate(reg["invoice_number"], STATUS_RED, f"invoice_number has unexpected format: {merged.invoice_number!r}")

    # ---- arithmetic + localization ----
    _check_arithmetic(merged, reg)

    # tax absent can be confirmed green when subtotal == total (tax = 0)
    if (
        merged.tax is None
        and merged.subtotal is not None
        and merged.total is not None
        and reg["tax"]["status"] == STATUS_AMBER
        and reg["subtotal"]["status"] == STATUS_GREEN
        and reg["total"]["status"] == STATUS_GREEN
        and _money_eq(merged.subtotal, merged.total)
    ):
        entry = reg["tax"]
        entry["status"] = STATUS_GREEN
        entry["conf"] = 0.8
        entry["reasons"] = [
            f"tax not found in either engine; subtotal == total ({merged.total:g}) confirms no tax"
        ]

    # ---- policy: green default reason ----
    default_reason = (
        "single engine: arithmetic and format checks pass"
        if single
        else "engines agree; arithmetic and format checks pass"
    )
    for entry in reg.values():
        if not entry["reasons"]:
            entry["reasons"].append(default_reason)

    # ---- assemble line_items group verdict ----
    row_keys = [k for k in reg if k.startswith("line_items[")]
    group = _new_entry(len(merged.line_items))
    for k in row_keys:
        _escalate(group, reg[k]["status"])
    if group_red_reason:
        _escalate(group, STATUS_RED, group_red_reason)
    if not merged.line_items:
        _escalate(group, STATUS_AMBER, "line_items: none found — cannot verify rows")
    if not group["reasons"]:
        group["reasons"].append(default_reason)
        group["status"] = STATUS_GREEN
    reg["line_items"] = group

    order = list(_SCALAR_FIELDS) + [k for k in reg if k.startswith("line_items[")] + ["line_items"]
    verdicts = [
        FieldVerdict(
            field=k,
            value=reg[k]["value"],
            status=reg[k]["status"],
            confidence=round(min(reg[k]["conf"], 1.0), 2),
            reasons=reg[k]["reasons"],
            hints=reg[k]["hints"],
        )
        for k in order
        if k in reg
    ]
    return VerificationResult(invoice=merged, verdicts=verdicts)
