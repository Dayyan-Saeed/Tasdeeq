"""Build tasdeeq_colab.zip — the upload artifact for notebooks/tasdeeq_eval.ipynb.

    python tools/build_colab_zip.py

Contains the evaluation code + tests + requirements and the full synth/out
dataset (ground truth + images + meta). Output: tasdeeq_colab.zip in repo root.
"""

import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent

CODE_FILES = [
    "requirements.txt",
    "eval/run_eval.py",
    "eval/quick_preprocess.py",
    "tasdeeq/extract.py",
    "tasdeeq/normalize.py",
    "tasdeeq/preprocess.py",
    "tasdeeq/schema.py",
    "tasdeeq/verify.py",
    "tasdeeq/__init__.py",
    "tasdeeq/engines/base.py",
    "tasdeeq/engines/easyocr_engine.py",
    "tasdeeq/engines/qaari.py",
    "tasdeeq/engines/tesseract_engine.py",
    "tasdeeq/engines/__init__.py",
    "tests/test_extract.py",
    "tests/test_normalize.py",
    "tests/test_verify.py",
]

DATASET_FILES = ("ground_truth.json", "image.png", "meta.json")


def main() -> None:
    out = ROOT / "tasdeeq_colab.zip"
    n_data = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in CODE_FILES:
            z.write(ROOT / f, f)
        for d in sorted((ROOT / "synth" / "out").iterdir()):
            if not d.is_dir():
                continue
            for f in DATASET_FILES:
                p = d / f
                if p.exists():
                    z.write(p, str(p.relative_to(ROOT)).replace("\\", "/"))
                    n_data += 1
    print(f"{out.name}: {out.stat().st_size:,} bytes ({len(CODE_FILES)} code + {n_data} dataset files)")


if __name__ == "__main__":
    main()
