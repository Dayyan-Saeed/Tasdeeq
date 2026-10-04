"""Quick preprocess benchmark: which input treatment extracts most fields?

Run: python -m eval.quick_preprocess [n_invoices]
Prints per-variant field-match counts against ground truth (dev set only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from tasdeeq.engines import get_engine
from tasdeeq.extract import extract_invoice
from tasdeeq.normalize import parse_amount

OUT = Path("synth/out")


def variants(img: Image.Image) -> dict[str, Image.Image]:
    long_side = max(img.size)
    out: dict[str, Image.Image] = {"raw": img}
    for target in (1400, 1800):
        s = target / long_side
        up = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
        out[f"up{target}"] = up
        # + Otsu binarization (approximated via numpy threshold)
        a = np.array(up.convert("L"))
        hist = np.bincount(a.ravel(), minlength=256)
        total = a.size
        sum_all = np.dot(np.arange(256), hist)
        sum_b = w_b = best = thr = 0
        for t in range(256):
            w_b += hist[t]
            if w_b == 0:
                continue
            w_f = total - w_b
            if w_f == 0:
                break
            sum_b += t * hist[t]
            m_b, m_f = sum_b / w_b, (sum_all - sum_b) / w_f
            var = w_b * w_f * (m_b - m_f) ** 2
            if var > best:
                best, thr = var, t
        binary = (a > thr).astype(np.uint8) * 255
        out[f"up{target}+otsu"] = Image.fromarray(binary, "L")
    return out


def score(inv, gt) -> tuple[int, int]:
    hits = 0
    checks = 0
    for field in ("invoice_number", "date", "total"):
        if gt.get(field) is None:
            continue
        checks += 1
        got, want = getattr(inv, field), gt[field]
        if field == "total":
            g, w = parse_amount(str(got)) if got is not None else None, parse_amount(str(want))
            ok = g is not None and w is not None and round(g, 2) == round(w, 2)
        else:
            ok = got == want
        hits += bool(ok)
    return hits, checks


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    engine_names = sys.argv[2].split(",") if len(sys.argv) > 2 else ["easyocr"]
    engines = {name: get_engine(name) for name in engine_names}
    dirs = sorted(d for d in OUT.iterdir() if (d / "ground_truth.json").exists())[:n]

    totals: dict[str, list[int]] = {}
    for d in dirs:
        gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("split") != "dev":
            continue
        img = Image.open(d / "image.png")
        for vname, vim in variants(img).items():
            for ename, eng in engines.items():
                key = f"{ename}|{vname}"
                try:
                    res = eng.read(vim)
                    inv, _ = extract_invoice(res)
                    hits, checks = score(inv, gt)
                except Exception as e:  # noqa: BLE001 — report engine failures
                    print(f"  ERROR {key}: {e}")
                    hits, checks = 0, 3
                totals.setdefault(key, [0, 0])
                totals[key][0] += hits
                totals[key][1] += checks

    print(f"\n{'variant':40s} {'hits':>6s} {'of':>4s} {'pct':>6s}")
    for key, (h, c) in sorted(totals.items(), key=lambda kv: -kv[1][0] / max(kv[1][1], 1)):
        print(f"{key:40s} {h:6d} {c:4d} {100 * h / max(c, 1):5.1f}%")


if __name__ == "__main__":
    main()
