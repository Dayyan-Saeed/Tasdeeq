"""Synthetic Urdu invoice generator.

Renders printed-style invoices with Noto Nastaliq Urdu (OFL) using real
OpenType shaping (uharfbuzz + freetype-py) — Pillow wheels lack libraqm and
the font has no Arabic Presentation Forms, so arabic-reshaper is not usable.

Direction model: every line is rendered base-LTR (runs in logical order,
Arabic runs shaped RTL internally). This keeps number runs left-to-right so a
dumb OCR reading order matches logical order for the label:value pairs, while
Urdu words still render as proper joined Nastaliq.

Outputs per invoice: image.png + ground_truth.json (arithmetically correct
values) + meta.json (degradation mode, digit style, corruption details).
Corrupted-total invoices keep the TRUE total in ground truth while printing a
wrong digit — that is what the verifier is supposed to catch.

CLI: python -m tasdeeq.synth.generate --n 100 --seed 42
"""
from __future__ import annotations

import argparse
import io
import json
import random
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import uharfbuzz as hb
from freetype import FT_LOAD_RENDER, Face
from PIL import Image, ImageDraw, ImageFilter

FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notonastaliqurdu/"
    "NotoNastaliqUrdu%5Bwght%5D.ttf"
)
FONT_PATH = Path(__file__).parent / "fonts" / "NotoNastaliqUrdu.ttf"

SHOP_NAMES = [
    "اشد سنٹری سٹور", "الفتح ٹریڈرز", "شہزادہ فارمیسی",
    "ملک ہارڈویئر", "رحمان کریانہ", "السلام سپر اسٹور",
    "جہان ڈھائیاں اسٹور", "برکت ٹریڈنگ کمپنی",
]
GROCERY = ["چینی", "آٹا", "چاول", "دال چنا", "دال مسور", "گھی", "تیل", "پتاتس", "پیاز", "ٹماٹر", "چائے", "بسکٹ", "دودھ"]
HARDWARE = ["پیچ", "نٹ", "وال ویش", "پائپ", "رنگ", "ہتھوڑا", "پینچس", "ڈبل ٹیپ", "کھڑا"]
PHARMACY = ["کیپسول", "شربت", "بینڈ اسٹریپ", "کریم", "ٹیبلٹ", "مسک", "آئینہ"]
ITEM_VOCAB = GROCERY + HARDWARE + PHARMACY

LABELS = {
    "invoice_number": ["انوائس نمبر", "بل نمبر"],
    "date": ["تاریخ"],
    "subtotal": ["مجموعی رقم"],
    "tax": ["سیلز ٹیکس", "وی اے ٹیکس"],
    "total": ["کل رقم"],
    "table_header": ["تفصیل تعداد شرح رقم"],
}

_URDU_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

# ---------------------------------------------------------------- shaping


class Shaper:
    def __init__(self, font_path: Path) -> None:
        self.font_path = str(font_path)
        blob = hb.Blob.from_file_path(self.font_path)
        self.hb_face = hb.Face(blob)
        self.hb_font = hb.Font(self.hb_face)
        self.ft_face = Face(self.font_path)
        self.upem = self.hb_face.upem
        self._glyph_cache: dict[tuple[int, int], tuple[np.ndarray, int, int]] = {}

    _NEUTRAL = set(" \t:،-–—_=/\\.,()[]{}%#*&+؟!«»\"'؟")

    @classmethod
    def runs(cls, text: str) -> list[tuple[str, str]]:
        """Split into (run, direction) with base-R neutral resolution.

        Arabic letters are RTL, digits/latin LTR; neutrals (space, colon,
        comma, hyphen...) join the neighbouring run of the same direction,
        or the RTL base direction when between different directions — so
        'بل نمبر: INV-...' shapes as rtl 'بل نمبر: ' + ltr 'INV-...'.
        """
        base = "rtl"
        dirs: list[str] = []
        for ch in text:
            cp = ord(ch)
            is_ar = (
                0x0600 <= cp <= 0x06FF or 0xFB50 <= cp <= 0xFDEF or 0xFE70 <= cp <= 0xFEFF
            ) and not (0x0660 <= cp <= 0x0669 or 0x06F0 <= cp <= 0x06F9)
            if is_ar:
                dirs.append("rtl")
            elif ch in cls._NEUTRAL or not ch.isalnum():
                dirs.append("neutral")
            else:
                dirs.append("ltr")

        # resolve neutrals: same-direction neighbours win, else base direction
        for i, d in enumerate(dirs):
            if d != "neutral":
                continue
            prev = next((dirs[j] for j in range(i - 1, -1, -1) if dirs[j] != "neutral"), None)
            nxt = next((dirs[j] for j in range(i + 1, len(dirs)) if dirs[j] != "neutral"), None)
            if prev and nxt and prev == nxt:
                dirs[i] = prev
            elif prev and nxt:  # different directions → base
                dirs[i] = base
            else:
                dirs[i] = prev or nxt or base

        runs: list[tuple[str, str]] = []
        for ch, d in zip(text, dirs):
            if runs and runs[-1][1] == d:
                runs[-1] = (runs[-1][0] + ch, d)
            else:
                runs.append((ch, d))
        return runs

    def _shape(self, text: str, direction: str):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        buf.direction = direction  # type: ignore[assignment]
        hb.shape(self.hb_font, buf)
        return buf.glyph_infos, buf.glyph_positions

    def width(self, text: str, size: int) -> float:
        return sum(self._run_width(r, d, size) for r, d in self.runs(text))

    def _run_width(self, run: str, direction: str, size: int) -> float:
        _, positions = self._shape(run, direction)
        return sum(p.x_advance for p in positions) * size / self.upem

    def _glyph(self, gid: int, size: int) -> tuple[np.ndarray, int, int]:
        key = (gid, size)
        if key not in self._glyph_cache:
            self.ft_face.set_pixel_sizes(0, size)
            self.ft_face.load_glyph(gid, FT_LOAD_RENDER)
            bm = self.ft_face.glyph.bitmap
            if bm.width and bm.rows:
                arr = np.frombuffer(bytes(bm.buffer), dtype=np.uint8).reshape(
                    bm.rows, abs(bm.pitch)
                )[:, : bm.width].copy()
            else:
                arr = np.zeros((0, 0), dtype=np.uint8)
            self._glyph_cache[key] = (arr, self.ft_face.glyph.bitmap_left, self.ft_face.glyph.bitmap_top)
        return self._glyph_cache[key]

    def draw(self, img: Image.Image, text: str, size: int, right: int, baseline: int,
              color: tuple[int, int, int] = (0, 0, 0)) -> None:
        """Draw one line, natural Urdu style: first logical run at the RIGHT.

        Runs are placed right-to-left in logical order (base-R bidi), while
        each run's glyphs keep their own internal visual order. This matches
        printed Urdu invoices so OCR engines trained on them emit logical text.
        """
        solid = Image.new("RGB", img.size, color)
        cum = 0.0
        for run, direction in self.runs(text):
            w = self._run_width(run, direction, size)
            pen = right - cum - w
            cum += w
            scale = size / self.upem
            infos, positions = self._shape(run, direction)
            for info, p in zip(infos, positions):
                arr, left, top = self._glyph(info.codepoint, size)
                if arr.size:
                    mask = Image.fromarray(arr, "L")
                    x0 = int(pen + p.x_offset * scale + left)
                    y0 = int(baseline - top - p.y_offset * scale)
                    sx0, sy0 = max(0, x0), max(0, y0)
                    sx1, sy1 = min(img.width, x0 + mask.width), min(img.height, y0 + mask.height)
                    if sx1 > sx0 and sy1 > sy0:
                        m = mask.crop((sx0 - x0, sy0 - y0, sx1 - x0, sy1 - y0))
                        img.paste(solid.crop((sx0, sy0, sx1, sy1)), (sx0, sy0), m)
                pen += p.x_advance * scale


def ensure_font() -> Path:
    if not FONT_PATH.exists():
        FONT_PATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)
    return FONT_PATH


# ---------------------------------------------------------------- content


@dataclass
class GeneratedInvoice:
    invoice_number: str
    date: str  # ISO
    line_items: list[dict]
    subtotal: float
    tax: Optional[float]
    total: float


def _digits(n: str, style: str) -> str:
    if style == "urdu":
        return n.translate(str.maketrans("0123456789", _URDU_DIGITS))
    return n


def _fmt_amount(v: float, style: str) -> str:
    if v == int(v):
        s = f"{int(v):,}"
    else:
        s = f"{v:,.2f}"
    return _digits(s, style)


def build_invoice(rng: random.Random) -> tuple[GeneratedInvoice, dict]:
    """Random fields + ground truth (arithmetically correct by construction)."""
    year = rng.choice([2024, 2025])
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    date_iso = f"{year:04d}-{month:02d}-{day:02d}"
    date_style = rng.random()
    if date_style < 0.7:
        date_printed = f"{day:02d}-{month:02d}-{year:04d}"
    else:
        date_printed = f"{year:04d}/{month:02d}/{day:02d}"

    inv_style = rng.random()
    if inv_style < 0.7:
        invoice_number = f"INV-{year}-{rng.randint(1, 9999):04d}"
    else:
        invoice_number = f"BL-{year}-{rng.randint(1, 9999):04d}"

    n_items = rng.randint(3, 6)
    items = []
    for _ in range(n_items):
        qty = rng.randint(1, 40)
        if rng.random() < 0.3:
            price = round(rng.randint(2, 400) + rng.choice([0.25, 0.5, 0.75]), 2)
        else:
            price = float(rng.randint(5, 1500))
        items.append({
            "description": rng.choice(ITEM_VOCAB),
            "quantity": float(qty),
            "unit_price": price,
            "line_total": round(qty * price, 2),
        })
    subtotal = round(sum(it["line_total"] for it in items), 2)
    rate = rng.choice([0.0, 0.13, 0.16, 0.17, 0.0, 0.13])
    tax = round(subtotal * rate, 2) if rate else None
    total = round(subtotal + (tax or 0.0), 2)

    inv = GeneratedInvoice(invoice_number, date_iso, items, subtotal, tax, total)
    meta = {"date_printed": date_printed, "tax_rate": rate}
    return inv, meta


# ---------------------------------------------------------------- render


def render_invoice(inv: GeneratedInvoice, meta: dict, shaper: Shaper, rng: random.Random,
                   digit_style: str, printed_total: Optional[str] = None) -> Image.Image:
    width = rng.randint(780, 920)
    margin = rng.randint(45, 70)
    big, mid = rng.randint(30, 40), rng.randint(24, 30)
    line_h = int(mid * 2.3)

    # assemble lines first to know canvas height
    header_size = big
    lines: list[tuple[str, int]] = [
        (rng.choice(SHOP_NAMES), header_size),
        (f"{LABELS['invoice_number'][rng.randrange(2)]}: {_digits(inv.invoice_number, digit_style)}", mid),
        (f"{LABELS['date'][0]}: {_digits(meta['date_printed'], digit_style)}", mid),
        (LABELS["table_header"][0], mid),
    ]
    col_qty = max(len(str(int(it["quantity"]))) for it in inv.line_items)
    col_rate = max(len(_fmt_amount(it["unit_price"], "western")) for it in inv.line_items)
    col_amt = max(len(_fmt_amount(it["line_total"], "western")) for it in inv.line_items)
    for it in inv.line_items:
        desc = it["description"]
        qty = _digits(str(int(it["quantity"])), digit_style).rjust(col_qty + 1)
        rate_s = _digits(_fmt_amount(it["unit_price"], "western"), digit_style).rjust(col_rate + 2)
        amt_s = _digits(_fmt_amount(it["line_total"], "western"), digit_style).rjust(col_amt + 2)
        lines.append((f"{desc}  {qty}  {rate_s}  {amt_s}", mid))
    lines.append((f"{LABELS['subtotal'][0]}: {_fmt_amount(inv.subtotal, digit_style)}", mid))
    if inv.tax is not None:
        lines.append((f"{LABELS['tax'][rng.randrange(2)]}: {_fmt_amount(inv.tax, digit_style)}", mid))
    total_str = printed_total if printed_total is not None else _fmt_amount(inv.total, digit_style)
    lines.append((f"{LABELS['total'][0]}: {total_str}", mid))

    height = margin * 2 + sum(int(s * 2.4) for _, s in lines) + 30
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = margin + line_h
    right = width - margin
    for idx, (text, size) in enumerate(lines):
        baseline = y
        shaper.draw(img, text, size, right, baseline)
        if idx == 0:
            draw.line([(margin, baseline + 14), (right, baseline + 14)], fill=(60, 60, 60), width=2)
            y += int(size * 2.6)
        else:
            y += int(size * 2.3)
    return img


# ---------------------------------------------------------------- degrade


def degrade(img: Image.Image, mode: str, rng: random.Random) -> Image.Image:
    if mode == "clean":
        return img
    if mode == "mild":
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.5, 1.1)))
        img = img.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor="white")
        arr = np.asarray(img).astype(np.int16)
        noise = np.random.default_rng(rng.getrandbits(32)).normal(0, rng.uniform(4, 8), arr.shape)
        return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    if mode == "heavy":
        w, h = img.size
        scale = rng.uniform(0.45, 0.6)
        img = img.resize((int(w * scale), int(h * scale)), Image.BILINEAR).resize((w, h), Image.BICUBIC)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.randint(30, 45))
        buf.seek(0)
        img = Image.open(buf).convert("RGB")
        arr = np.asarray(img).astype(np.float32)
        gx = np.linspace(rng.uniform(0.5, 0.75), 1.0, arr.shape[1])[None, :, None]
        gy = np.linspace(rng.uniform(0.6, 0.9), 1.0, arr.shape[0])[:, None, None]
        arr *= np.minimum(gx, gy)
        noise = np.random.default_rng(rng.getrandbits(32)).normal(0, rng.uniform(8, 14), arr.shape)
        return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8))
    raise ValueError(f"unknown mode {mode}")


def corrupt_digit(s: str, rng: random.Random) -> str:
    digits_at = [i for i, c in enumerate(s) if c.isdigit()]
    if not digits_at:
        return s
    pos = rng.choice(digits_at)
    old = s[pos]
    new = rng.choice([d for d in "0123456789" if d != old])
    return s[:pos] + new + s[pos + 1:]


# ---------------------------------------------------------------- driver


def generate(n: int, out_dir: Path, seed: int, shaper: Optional[Shaper] = None) -> list[Path]:
    rng = random.Random(seed)
    shaper = shaper or Shaper(ensure_font())
    # stratified modes so the held-out eval slice contains corrupted totals
    dev_n, eval_n = n - min(20, n // 5), min(20, n // 5)
    dev_modes = ["clean"] * int(dev_n * 0.35) + ["mild"] * int(dev_n * 0.30) \
        + ["heavy"] * int(dev_n * 0.25)
    dev_modes += ["corrupted"] * (dev_n - len(dev_modes))
    eval_modes = ["clean"] * int(eval_n * 0.40) + ["mild"] * int(eval_n * 0.25) \
        + ["heavy"] * int(eval_n * 0.15)
    eval_modes += ["corrupted"] * (eval_n - len(eval_modes))
    rng.shuffle(dev_modes)
    rng.shuffle(eval_modes)
    modes = dev_modes + eval_modes
    written: list[Path] = []
    for i in range(n):
        mode = modes[i]
        inv, meta = build_invoice(rng)
        digit_style = "urdu" if rng.random() < 0.5 else "western"
        printed_total = None
        if mode == "corrupted":
            true_total = _fmt_amount(inv.total, "western")
            printed_total = _digits(corrupt_digit(true_total, rng), digit_style)
        img = render_invoice(inv, meta, shaper, rng, digit_style, printed_total=printed_total)
        img = degrade(img, "clean" if mode == "corrupted" else mode, rng)

        d = out_dir / f"{i:04d}"
        d.mkdir(parents=True, exist_ok=True)
        img.save(d / "image.png")
        (d / "ground_truth.json").write_text(
            json.dumps(
                {
                    "invoice_number": inv.invoice_number,
                    "date": inv.date,
                    "line_items": inv.line_items,
                    "subtotal": inv.subtotal,
                    "tax": inv.tax,
                    "total": inv.total,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "mode": mode,
                    "split": "eval" if i >= dev_n else "dev",
                    "digit_style": digit_style,
                    "printed_total": printed_total,
                    "date_printed": meta["date_printed"],
                    "tax_rate": meta["tax_rate"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        written.append(d)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic Urdu invoices")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "synth" / "out")
    args = ap.parse_args()
    paths = generate(args.n, args.out, args.seed)
    eval_count = sum(1 for p in paths if json.loads((p / "meta.json").read_text(encoding="utf-8"))["split"] == "eval")
    print(f"generated {len(paths)} invoices in {args.out} ({eval_count} held out for eval)")


if __name__ == "__main__":
    main()
