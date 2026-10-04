"""Generate the static fallback page (docs/index.html) from measured results.

    python tools/build_static_fallback.py

Shows three saved pipeline examples (green / amber / red) from results/results.json
so a working showcase exists even when the live Space is down (spec §9).
"""

import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"

# (invoice id, caption explaining the verdict story)
EXAMPLES = [
    ("0091", "All checks pass: arithmetic, format and both engines agree — safe to auto-accept."),
    (
        "0087",
        "Arithmetic passes but engines disagree on a field — amber: a human must review "
        "before anything is accepted.",
    ),
    (
        "0099",
        "Corrupted invoice: the printed total (74,410.52) is wrong — red blocks "
        "auto-accept. Ground-truth total: 74,910.52.",
    ),
]
_COLORS = {"green": "#1a7f37", "amber": "#9a6700", "red": "#cf222e"}


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _verdict_table(verdicts: dict) -> str:
    rows = []
    for field, v in verdicts.items():
        c = _COLORS[v["status"]]
        rows.append(
            f"<tr><td><code>{field}</code></td>"
            f"<td style='color:{c};font-weight:600'>● {v['status']}</td>"
            f"<td style='text-align:right' dir='auto'>{_fmt(v.get('value'))}</td></tr>"
        )
    return (
        "<table>"
        "<tr><th>field</th><th>status</th><th>value</th></tr>" + "".join(rows) + "</table>"
    )


def main() -> None:
    data = json.loads((ROOT / "results" / "results.json").read_text(encoding="utf-8"))
    pipeline = data["setups"]["pipeline"]
    rows = {r["invoice"]: r for r in data["rows"]["pipeline"]}

    ASSETS.mkdir(parents=True, exist_ok=True)
    cards = []
    for inv, caption in EXAMPLES:
        r = rows[inv]
        worst = r["overall_worst"]
        shutil.copy(ROOT / "synth" / "out" / inv / "image.png", ASSETS / f"{inv}.png")
        cards.append(
            f"""
    <section class="card">
      <div class="card-head">
        <span class="chip" style="background:{_COLORS[worst]}">{worst.upper()}</span>
        <span class="mode">{inv} · {r['mode']} invoice · saved eval run</span>
      </div>
      <div class="card-body">
        <img src="assets/{inv}.png" alt="invoice {inv}">
        <div>{_verdict_table(r['verdicts'])}<p class="caption">{caption}</p></div>
      </div>
    </section>"""
        )

    metrics = (
        f"<div class='metric'><b>{pipeline['green_precision']:.1f}</b><span>green precision</span></div>"
        f"<div class='metric'><b>{pipeline['flag_rate_on_wrong']:.1f}</b><span>flag rate on wrong</span></div>"
        f"<div class='metric'><b>{pipeline['error_recall_corrupted']:.1f}</b><span>corrupted recall</span></div>"
        f"<div class='metric'><b>{pipeline['verifier_accuracy']:.0%}</b><span>verifier accuracy</span></div>"
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tasdeeq — verified Urdu invoice extraction</title>
<style>
  :root {{ font-family: system-ui, sans-serif; color: #1f2328; }}
  body {{ margin: 0; background: #f6f8fa; }}
  header, main, footer {{ max-width: 980px; margin: 0 auto; padding: 16px; }}
  header {{ padding-top: 40px; }}
  h1 {{ margin: 0 0 6px; }}
  .sub {{ color: #57606a; margin: 0 0 18px; }}
  .note {{ background: #fff8c5; border: 1px solid #d4a72c66; border-radius: 8px;
           padding: 10px 14px; font-size: .92em; }}
  .metrics {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 18px 0; }}
  .metric {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
             padding: 10px 16px; text-align: center; min-width: 130px; }}
  .metric b {{ display: block; font-size: 1.6em; color: #1a7f37; }}
  .metric span {{ font-size: .8em; color: #57606a; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 10px;
           margin: 18px 0; overflow: hidden; }}
  .card-head {{ display: flex; align-items: center; gap: 10px; padding: 10px 14px;
                border-bottom: 1px solid #d0d7de; }}
  .chip {{ color: #fff; font-weight: 700; font-size: .78em; border-radius: 999px;
           padding: 3px 10px; }}
  .mode {{ color: #57606a; font-size: .85em; }}
  .card-body {{ display: grid; grid-template-columns: 1fr 1.2fr; gap: 16px; padding: 14px; }}
  .card-body img {{ width: 100%; border: 1px solid #d0d7de; border-radius: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .92em; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; }}
  .caption {{ color: #57606a; font-size: .88em; line-height: 1.45; }}
  footer {{ color: #57606a; font-size: .85em; padding-bottom: 48px; }}
  a {{ color: #0969da; }}
  @media (max-width: 760px) {{ .card-body {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>Tasdeeq — verified Urdu (Nastaliq) invoice extraction</h1>
  <p class="sub">Two OCR engines read the invoice; a verification layer (arithmetic,
  cross-engine agreement, format validity) decides green / amber / red per field.
  Nothing is ever auto-corrected.</p>
  <p class="note">This is the <b>static fallback</b> showcase with saved example results.
  The live app (login <code>demo / tasdeeq123</code>) runs at
  <a href="https://huggingface.co/spaces/dayyan003/Tasdeeq">huggingface.co/spaces/dayyan003/Tasdeeq</a>
  — source code at <a href="https://github.com/Dayyan-Saeed/Tasdeeq">github.com/Dayyan-Saeed/Tasdeeq</a>.</p>
  <div class="metrics">{metrics}</div>
  <p class="sub">Held-out evaluation, pipeline (Qaari + EasyOCR), 20 synthetic invoices
  (the main set is synthetic; see the README for limits).</p>
</header>
<main>{''.join(cards)}</main>
<footer>Sample invoices are synthetic renders (seed 42). Verdicts are the measured
output of the evaluation run saved in <code>results/results.md</code>.</footer>
</body>
</html>
"""
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    print(f"docs/index.html written ({len(html):,} bytes), {len(EXAMPLES)} examples")


if __name__ == "__main__":
    main()
