"""Held-out evaluation (spec §8).

Runs each engine once over the eval split, then scores three setups:
Engine A alone, Engine B alone, and the full verified pipeline (A+B).

Raw OCR lines are cached in results/raw_cache.json: re-running after an
extraction/verify change re-scores from cache without re-running OCR.

Usage (local CPU baseline):
    python -m eval.run_eval --engines easyocr,tesseract
Usage (Colab GPU):
    python -m eval.run_eval --engines qaari,easyocr

Writes results/results.md and results/results.json.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from tasdeeq.engines import get_engine
from tasdeeq.extract import extract_invoice
from tasdeeq.normalize import iso_date, parse_amount
from tasdeeq.preprocess import preprocess
from tasdeeq.schema import OCRResult
from tasdeeq.verify import verify

OUT_DIR = Path("results")
SCALARS = ("invoice_number", "date", "subtotal", "tax", "total")
_RANK = {"green": 0, "amber": 1, "red": 2, "missing": 2}


def value_correct(field: str, got, gt) -> bool:
    if field == "invoice_number":
        return got is not None and gt is not None and str(got) == str(gt)
    if field == "date":
        if got is None or gt is None:
            return False
        return (iso_date(str(got)) or str(got)) == (iso_date(str(gt)) or str(gt))
    g = parse_amount(str(got)) if got is not None else None
    w = parse_amount(str(gt)) if gt is not None else None
    if g is None or w is None:
        return got is None and gt is None
    return round(g, 2) == round(w, 2)


def score_with_verdicts(
    results: list, gts: list[dict], metas: list[dict]
) -> tuple[dict, list[dict]]:
    """Score a setup: VerificationResults (each holds its merged Invoice) vs ground truth."""
    field_hits = {f: 0 for f in list(SCALARS) + ["line_items_count"]}
    green = green_ok = correct_verdicts = wrong_fields = flagged_incorrect = 0
    corrupted_total = corrupted_flagged = 0
    rows = []

    for res, gt, meta in zip(results, gts, metas):
        inv = res.invoice
        vm = res.verdict_map()
        acc = {
            **{f: value_correct(f, getattr(inv, f), gt.get(f)) for f in SCALARS},
            "line_items_count": len(inv.line_items) == len(gt.get("line_items", [])),
        }
        for f, ok in acc.items():
            field_hits[f] += bool(ok)

        field_stats = {}
        for f in SCALARS:
            st = vm[f].status if f in vm else "missing"
            ok = acc[f]
            is_green = st == "green"
            if is_green:
                green += 1
                green_ok += int(ok)
            if is_green == bool(ok):
                correct_verdicts += 1
            if not ok:
                wrong_fields += 1
                flagged_incorrect += int(not is_green)
            field_stats[f] = {"status": st, "correct": ok, "value": vm[f].value if f in vm else None}

        is_corrupt = meta.get("mode") == "corrupted"
        if is_corrupt:
            corrupted_total += 1
            st = field_stats["total"]["status"]
            corrupted_flagged += int(st != "green")

        rows.append(
            {
                "invoice": meta["id"],
                "mode": meta.get("mode"),
                "printed_total": meta.get("printed_total"),
                "gt_total": gt.get("total"),
                "acc": acc,
                "verdicts": field_stats,
                "overall_worst": max(
                    (field_stats[f]["status"] for f in ("invoice_number", "date", "total")),
                    key=lambda s: _RANK[s],
                ),
            }
        )

    n = len(results) or 1
    total_fields = n * len(SCALARS)
    metrics = {
        "invoices": n,
        "field_accuracy": {f: round(hits / n, 3) for f, hits in field_hits.items()},
        "green_fields": green,
        "green_precision": round(green_ok / green, 3) if green else None,
        "wrong_fields": wrong_fields,
        "flag_rate_on_wrong": round(flagged_incorrect / wrong_fields, 3) if wrong_fields else None,
        "verifier_accuracy": round(correct_verdicts / total_fields, 3),
        "error_recall_corrupted": round(corrupted_flagged / corrupted_total, 3)
        if corrupted_total
        else None,
        "corrupted_invoices": corrupted_total,
    }
    return metrics, rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", default="easyocr,tesseract")
    ap.add_argument("--split", default="eval")
    ap.add_argument("--out", default=str(OUT_DIR / "results.md"))
    ap.add_argument("--limit", type=int, default=0, help="only first N invoices (smoke runs)")
    ap.add_argument(
        "--raw-cache",
        default=str(OUT_DIR / "raw_cache.json"),
        help="reuse saved raw OCR lines per engine/invoice; saves new reads here",
    )
    args = ap.parse_args()

    cache_path = Path(args.raw_cache)
    cache: dict = {"engines": {}}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache.setdefault("engines", {})

    engine_names = [e.strip() for e in args.engines.split(",") if e.strip()]
    engines = {n: get_engine(n) for n in engine_names}
    base = Path("synth/out")
    inv_dirs = sorted(d for d in base.iterdir() if (d / "ground_truth.json").exists())

    gts, metas = [], []
    extracted: dict[str, list] = {n: [] for n in engine_names}
    latencies: dict[str, list[float]] = {n: [] for n in engine_names}

    for d in inv_dirs:
        gt = json.loads((d / "ground_truth.json").read_text(encoding="utf-8"))
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        if meta.get("split") != args.split:
            continue
        if args.limit and len(gts) >= args.limit:
            break
        meta = dict(meta)
        meta["id"] = d.name
        gts.append(gt)
        metas.append(meta)
        img = preprocess(Image.open(d / "image.png").convert("RGB"))
        for name, eng in engines.items():
            eng_cache = cache["engines"].setdefault(name, {"lines": {}, "latency_ms": {}})
            if d.name in eng_cache["lines"]:
                cached_lines = eng_cache["lines"][d.name]
                ocr_res = OCRResult(engine=name, text="\n".join(cached_lines), lines=cached_lines)
                if d.name in eng_cache["latency_ms"]:
                    latencies[name].append(eng_cache["latency_ms"][d.name])
            else:
                t0 = time.perf_counter()
                ocr_res = eng.read(img)
                elapsed = (time.perf_counter() - t0) * 1000
                latencies[name].append(elapsed)
                eng_cache["lines"][d.name] = ocr_res.lines
                eng_cache["latency_ms"][d.name] = round(elapsed, 1)
            extracted[name].append(extract_invoice(ocr_res)[0])

    if args.raw_cache:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    # setups: each engine alone + pipeline of the first two engines
    setups: dict[str, list[str]] = {n: [n] for n in engine_names}
    if len(engine_names) >= 2:
        setups["pipeline"] = engine_names[:2]

    all_metrics: dict[str, dict] = {}
    all_rows: dict[str, list] = {}
    for setup_name, members in setups.items():
        results = []
        for i in range(len(gts)):
            if len(members) == 1:
                results.append(verify(extracted[members[0]][i]))
            else:
                results.append(
                    verify(extracted[members[0]][i], extracted[members[1]][i])
                )
        metrics, rows = score_with_verdicts(results, gts, metas)
        metrics["setup"] = setup_name
        metrics["engines"] = members
        all_metrics[setup_name] = metrics
        all_rows[setup_name] = rows

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "split": args.split,
        "engines": engine_names,
        "latency_ms": {
            name: {
                "mean": round(statistics.mean(v), 1) if v else None,
                "median": round(statistics.median(v), 1) if v else None,
                "max": round(max(v), 1) if v else None,
            }
            for name, v in latencies.items()
        },
        "setups": all_metrics,
        "rows": all_rows,
    }
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_markdown(args.out, payload)
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, ensure_ascii=False, indent=2))


def write_markdown(path: str, p: dict) -> None:
    lines = [
        "# Tasdeeq evaluation results",
        "",
        f"- generated: {p['generated_at']}",
        f"- engines: {', '.join(p['engines'])}  |  split: {p['split']} ({p['setups'][next(iter(p['setups']))]['invoices']} invoices)",
        "",
        "## Setup comparison",
        "",
        "| setup | field acc (num/date/total) | verifier acc | green precision | flag rate on wrong | corrupted recall |",
        "|---|---|---|---|---|---|",
    ]
    for name, m in p["setups"].items():
        fa = m["field_accuracy"]
        lines.append(
            f"| {name} | {fa['invoice_number']:.0%}/{fa['date']:.0%}/{fa['total']:.0%} "
            f"| {m['verifier_accuracy']:.0%} | {m['green_precision']} "
            f"| {m['flag_rate_on_wrong']} | {m['error_recall_corrupted']} |"
        )
    lines += ["", "## Latency (ms)", "", "| engine | mean | median | max |", "|---|---|---|---|"]
    for name, lat in p["latency_ms"].items():
        lines.append(f"| {name} | {lat['mean']} | {lat['median']} | {lat['max']} |")

    for setup, rows in p["rows"].items():
        lines += [
            "",
            f"## Setup: {setup}",
            "",
            "| invoice | mode | invoice_no | date | total | items | overall |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            def cell(f: str) -> str:
                v = r["verdicts"].get(f, {})
                mark = {"green": "G", "amber": "A", "red": "R"}.get(v.get("status", "?"), "?")
                return f"{mark}{'✓' if v.get('correct') else '✗'}"

            lines.append(
                f"| {r['invoice']} | {r['mode']} | {cell('invoice_number')} | {cell('date')} "
                f"| {cell('total')} | {'✓' if r['acc']['line_items_count'] else '✗'} "
                f"| {r['overall_worst']} |"
            )
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
