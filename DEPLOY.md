# Deployment

Two deliverables (spec §9): a live HF Space (Gradio + ZeroGPU) with the demo
login, and a static fallback page — already live at
<https://dayyan-saeed.github.io/Tasdeeq/>.

## 1. Hugging Face Space (live app)

Tooling comes from the official [hf CLI](https://huggingface.co/docs/huggingface_hub/guides/cli)
+ the [huggingface-spaces skill](https://github.com/huggingface/skills/tree/main/skills/huggingface-spaces).

### Status (2026-10-03)

- Account `dayyan003` got **402** creating the ZeroGPU Gradio Space — the free
  ZeroGPU tier needs an account >30 days old (or PRO, or a community grant).
- **Chose the grant path.** Created a **static holding Space** (free for every
  account) with the full app code pushed and the showcase page served:
  - Space: <https://huggingface.co/spaces/dayyan003/Tasdeeq>
    (serves <https://dayyan003-tasdeeq.static.hf.space>)
  - Grant application: Community tab discussion #1,
    "Apply for a GPU community grant: Personal project" (submitted
    2026-10-03, approval takes days).
- Everything below the flip is already in place: code is ZeroGPU-compliant,
  `space/README.md` has the gradio frontmatter, `space/README-static.md` is
  the holding-page README actually deployed.

### Flip to Gradio (after the grant is approved)

```powershell
cd <your clone of Tasdeeq>
python tools\build_space.py          # stages build/space/ with sdk: gradio README
hf upload dayyan003/Tasdeeq build\space . --repo-type space
```

PowerShell note: do **not** pass `--exclude "**/__pycache__/**"` to `hf upload`
— PowerShell expands the glob into stray arguments; `build_space.py` already
strips `__pycache__`.

Files that drive the build (all inside `build/space/`):

- `README.md` — from `space/README.md`: required YAML frontmatter
  (`sdk: gradio`, `sdk_version: 6.29.1`, `python_version: "3.12"`, login hint).
- `requirements.txt` — from `space/requirements.txt`: **no** gradio / spaces /
  torch (platform-provided); `torchvision` unpinned (EasyOCR needs it).
- `app.py` — on Spaces: `import spaces` first, both engines warmed up at
  module scope, the Gradio-bound `run_pipeline` itself carries
  `@spaces.GPU(duration=180)`, EasyOCR pinned to CPU (the ZeroGPU main process
  has no real GPU), login `demo / tasdeeq123`.

### Verify (do not trust RUNNING alone)

After the flip:

```powershell
hf spaces info dayyan003/Tasdeeq --expand runtime   # stage + hardware
hf spaces logs dayyan003/Tasdeeq --tail 200         # startup clean?
```

Then open <https://huggingface.co/spaces/dayyan003/Tasdeeq> → login → run a
sample → edit a value cell → Export CSV.

### Iterating

- Python-only edit: re-run `python tools\build_space.py` + `hf upload ...`
  (the platform hot-reloads pure-Python changes).
- `requirements.txt` / frontmatter change: same upload triggers a full rebuild.
- First request includes a model cold start (Qaari base ≈5 GB download on
  first build; adapter + weights stream into VRAM per cold worker).

### Duration calibration (ZeroGPU)

`duration=180` in `app.py` is a placeholder. Per the skill: the handler
already reports per-engine latency in `meta` — run 2-3 calls on the live Space
(measured on T4: mean 61 s, max 196 s; Blackwell should be faster), then set
`duration = round(measured_max × 1.4)` and re-upload. Symptoms of a wrong
value: `ZeroGPU illegal duration` (too high for the visitor tier) or a task
truncated mid-generation (too low).

### Limits to state honestly

- **Quota**: each Qaari read reserves the full declared duration from the
  visitor's daily ZeroGPU quota (~5 min free tier) — expect ~1-2 full reads
  per free visitor per day.
- **Graceful degradation**: if the GPU call fails, the UI shows the engine
  error in `meta` and the verdicts fall back to single-engine (amber-heavy).

## 2. GitHub Pages (static fallback) — DONE

1. <https://github.com/Dayyan-Saeed/Tasdeeq/settings/pages> → branch `main`,
   folder `/docs`.
2. Live: <https://dayyan-saeed.github.io/Tasdeeq/> — three saved pipeline
   examples from the measured eval, regenerated with
   `python tools/build_static_fallback.py`.

## 3. Definition-of-done checks (spec §11)

- [ ] **Static holding Space live + grant submitted** (2026-10-03)
- [ ] Space flips to Gradio after grant approval; login `demo / tasdeeq123` works
- [ ] One sample extraction returns a verdict table; edit + export works
- [ ] Pages URL loads with the three saved examples (verified 2026-10-03)
- [ ] `duration` calibrated from measured live latencies
