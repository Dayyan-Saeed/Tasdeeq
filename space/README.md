---
title: Tasdeeq
emoji: "\U0001F9FE"
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 6.29.1
app_file: app.py
pinned: false
license: mit
python_version: "3.12"
short_description: Verified Urdu Nastaliq invoice OCR with field verdicts
startup_duration_timeout: 30m
---

# Tasdeeq — verified Urdu invoice OCR

Two engines read the invoice (Qaari on ZeroGPU + EasyOCR on CPU); the
verification layer checks arithmetic, cross-engine agreement and format
validity and gives every field a **green / amber / red** verdict. Nothing is
auto-corrected.

**Login:** `demo` / `tasdeeq123`

- Source, evaluation and limits: <https://github.com/Dayyan-Saeed/Tasdeeq>
- Static fallback (saved results): <https://dayyan-saeed.github.io/Tasdeeq/>

Qaari runs under `@spaces.GPU` (first request includes a model cold start;
free-tier ZeroGPU quota limits GPU reads per day). If the GPU call fails, the
app degrades to EasyOCR-only and shows the error in the UI.
