"""Tasdeeq demo — upload an Urdu invoice, get verified fields.

Local (CPU):      EasyOCR + Tesseract behind the same interface.
On a HF Space:    Qaari (ZeroGPU) + EasyOCR. The Gradio-bound handler itself
                  carries @spaces.GPU — the ZeroGPU startup scan requires the
                  decorated function to be the one wired to the event — and
                  models are warmed up at module scope so startup packs them.

Run locally:   python app.py
Deploy:        DEPLOY.md (hf CLI flow), tools/build_space.py stages the upload
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

ON_SPACES = bool(os.getenv("SPACE_ID"))
if ON_SPACES:
    # ZeroGPU rule 1: spaces must be imported before any torch/CUDA-touching
    # code — it monkey-patches torch.cuda.* for the whole main process.
    import spaces

import gradio as gr
import pandas as pd
from PIL import Image

from tasdeeq.engines import get_engine
from tasdeeq.extract import extract_invoice
from tasdeeq.preprocess import preprocess
from tasdeeq.schema import STATUS_AMBER, STATUS_GREEN, STATUS_RED, VerificationResult
from tasdeeq.verify import verify

ENGINE_NAMES = ["qaari", "easyocr"] if ON_SPACES else ["easyocr", "tesseract"]
# The ZeroGPU main process has no real GPU (only spaces' patched view), and
# EasyOCR runs as plain CPU code in the same process as the handler — so pin
# it to CPU there; inference then works identically in main and GPU worker.
_ENGINE_KW = {"easyocr": {"gpu": False}} if ON_SPACES else {}
_ENGINE_NOTE = (
    "GPU Space: Qaari (ZeroGPU) + EasyOCR"
    if ON_SPACES
    else "No GPU here — running CPU fallback: EasyOCR + Tesseract (registry swap: get_engine)"
)
_RANK = {STATUS_GREEN: 0, STATUS_AMBER: 1, STATUS_RED: 2}
_COLORS = {STATUS_GREEN: "#1a7f37", STATUS_AMBER: "#9a6700", STATUS_RED: "#cf222e"}
_BADGE = {STATUS_GREEN: "●", STATUS_AMBER: "●", STATUS_RED: "●"}
SAMPLES = sorted(str(p) for p in Path("synth/out").glob("*/image.png"))

_cache: dict[str, object] = {}


def _engine(name: str):
    if name not in _cache:
        _cache[name] = get_engine(name, **_ENGINE_KW.get(name, {}))
    return _cache[name]


if ON_SPACES:
    # ZeroGPU rule 2: eager module-scope load — startup packs the weights to
    # disk and the GPU worker streams them in; lazy loading inside the handler
    # would pay checkpoint I/O on every cold request.
    for _name in ENGINE_NAMES:
        _engine(_name).warmup()


def _read(name: str, image: Image.Image):
    t0 = time.perf_counter()
    try:
        res = _engine(name).read(image)
        err = None
    except Exception as e:  # noqa: BLE001 — degrade instead of crashing the demo
        res, err = None, f"{name} failed: {e}"
    return res, (time.perf_counter() - t0) * 1000, err


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _worst(result: VerificationResult) -> str:
    vm = result.verdict_map()
    keys = [k for k in ("invoice_number", "date", "subtotal", "tax", "total", "line_items") if k in vm]
    return max((vm[k].status for k in keys), key=lambda s: _RANK[s])


def _verdict_table(result: VerificationResult) -> str:
    rows = []
    for v in result.verdicts:
        color = _COLORS.get(v.status, "#000")
        hints = "<br>".join(v.hints) if v.hints else ""
        reasons = "; ".join(v.reasons)
        rows.append(
            f"<tr>"
            f"<td><code>{v.field}</code></td>"
            f"<td style='color:{color};font-weight:600'>{_BADGE.get(v.status, '')} {v.status}</td>"
            f"<td style='text-align:right'>{_fmt(v.value)}</td>"
            f"<td>{v.confidence:.2f}</td>"
            f"<td style='font-size:0.85em'>{reasons}{('<br><b>' + hints + '</b>') if hints else ''}</td>"
            f"</tr>"
        )
    return (
        "<table style='width:100%;border-collapse:collapse'>"
        "<tr style='text-align:left;border-bottom:2px solid #d0d7de'>"
        "<th>field</th><th>status</th><th>value</th><th>conf</th><th>reasons / hints</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _fields_df(result: VerificationResult) -> pd.DataFrame:
    """Field table with an editable value column (spec §9: edit flagged cells)."""
    rows = [
        [v.field, v.status, _fmt(v.value), "; ".join(v.reasons)]
        for v in result.verdicts
    ]
    return pd.DataFrame(rows, columns=["field", "status", "value", "reasons"])


def _export_file(df: pd.DataFrame, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="tasdeeq_")
    with os.fdopen(fd, "w", encoding="utf-8-sig" if suffix == ".csv" else "utf-8") as f:
        if suffix == ".csv":
            df.to_csv(f, index=False)
        else:
            json.dump(df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    return path


def export_csv(df: pd.DataFrame) -> str:
    """Download the (possibly edited) field table as CSV."""
    return _export_file(df, ".csv")


def export_json(df: pd.DataFrame) -> str:
    """Download the (possibly edited) field table as JSON records."""
    return _export_file(df, ".json")


def run_pipeline(image: Image.Image | None):
    """Read the invoice with both engines and return verified per-field verdicts."""
    if image is None:
        raise gr.Error("Upload an invoice image (or pick a sample).")
    img = preprocess(image.convert("RGB"))

    reads = {}
    latencies = {}
    errors = []
    for name in ENGINE_NAMES:
        res, ms, err = _read(name, img)
        latencies[name] = round(ms)
        if err:
            errors.append(err)
        if res is not None:
            reads[name] = res

    if not reads:
        raise gr.Error("Both engines failed: " + " | ".join(errors))

    inv_a_name = ENGINE_NAMES[0]
    a = extract_invoice(reads[inv_a_name])[0] if inv_a_name in reads else None
    b = (
        extract_invoice(reads[ENGINE_NAMES[1]])[0]
        if len(ENGINE_NAMES) > 1 and ENGINE_NAMES[1] in reads
        else None
    )
    if a is None:
        a, b = b, None
    result = verify(a, b)

    status = _worst(result)
    banner = (
        f"<div style='padding:14px 18px;border-radius:8px;font-size:1.15em;font-weight:700;"
        f"color:#fff;background:{_COLORS[status]}'>"
        f"Overall: {status.upper()} — "
        + {
            STATUS_GREEN: "all checks passed, safe to auto-accept",
            STATUS_AMBER: "needs human review of flagged fields",
            STATUS_RED: "blocking issues found — do not auto-accept",
        }[status]
        + "</div>"
    )
    used = ", ".join(reads) + (" (fallback single-engine)" if len(reads) == 1 else "")
    meta = (
        f"engines: **{used}** &nbsp;|&nbsp; latency: "
        + ", ".join(f"{k} {v}ms" for k, v in latencies.items())
        + (f" &nbsp;|&nbsp; ⚠ {'; '.join(errors)}" if errors else "")
    )
    texts = {name: reads[name].text for name in reads}
    return (
        banner,
        meta,
        _verdict_table(result),
        _fields_df(result),
        texts.get(ENGINE_NAMES[0], ""),
        texts.get(ENGINE_NAMES[1], "(engine unavailable)"),
    )


if ON_SPACES:
    # ZeroGPU rule 3: decorate the exact function Gradio binds — the startup
    # scan looks for @spaces.GPU on registered event handlers and raises
    # "No @spaces.GPU function detected" otherwise. duration=180 is a
    # placeholder until measured on the live Space (see DEPLOY.md).
    run_pipeline = spaces.GPU(duration=180)(run_pipeline)

with gr.Blocks(title="Tasdeeq — verified Urdu invoice OCR") as demo:
    gr.Markdown(
        "# Tasdeeq — verified Urdu invoice OCR\n"
        "Two independent engines read the invoice; the verification layer checks "
        "arithmetic, engine agreement and format validity. **Green = auto-accept, "
        "amber/red = human review.** Nothing is ever auto-corrected.\n\n"
        + f"`{_ENGINE_NOTE}`"
    )
    with gr.Row():
        with gr.Column(scale=1):
            img_in = gr.Image(type="pil", label="Invoice photo / scan")
            if SAMPLES:
                gr.Examples(
                    examples=[[p] for p in SAMPLES[:3]],
                    inputs=img_in,
                    label="Sample invoices",
                )
            run_btn = gr.Button("Read & verify", variant="primary")
        with gr.Column(scale=2):
            banner = gr.HTML(label="overall")
            meta = gr.Markdown()
            table = gr.HTML()
            fields = gr.Dataframe(
                headers=["field", "status", "value", "reasons"],
                label="Extracted fields — edit the value cells to correct OCR, then export",
                interactive=True,
            )
            with gr.Row():
                csv_btn = gr.Button("Export CSV")
                json_btn = gr.Button("Export JSON")
            out_file = gr.File(label="download")
            with gr.Accordion("Engine raw outputs", open=False):
                txt_a = gr.Textbox(label="Engine 1", lines=14, rtl=True)
                txt_b = gr.Textbox(label="Engine 2", lines=14, rtl=True)

    outputs = [banner, meta, table, fields, txt_a, txt_b]
    run_btn.click(run_pipeline, inputs=img_in, outputs=outputs)
    img_in.change(run_pipeline, inputs=img_in, outputs=outputs)
    csv_btn.click(export_csv, inputs=fields, outputs=out_file)
    json_btn.click(export_json, inputs=fields, outputs=out_file)

if __name__ == "__main__":
    demo.launch(auth=("demo", "tasdeeq123"), mcp_server=True)
