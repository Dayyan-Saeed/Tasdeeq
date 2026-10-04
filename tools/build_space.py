"""Assemble the HF Space upload folder.

    python tools/build_space.py            ->  build/space/   (Gradio SDK)
    python tools/build_space.py --static   ->  build/space/   (static holding
                                                page + full app code, used
                                                while the GPU grant is pending)

Contains app.py, the tasdeeq package (without the 23 MB tesseract data — the
Space never runs Tesseract), the 3 sample invoices, and space/{README,requirements}
so `hf upload` can push the folder as a Space repo. --static additionally
embeds docs/index.html as the served showcase page.
"""

import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "space"


def main() -> None:
    static = "--static" in sys.argv[1:]
    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "synth").mkdir(parents=True)

    shutil.copy2(ROOT / "app.py", BUILD / "app.py")
    readme = "README-static.md" if static else "README.md"
    shutil.copy2(ROOT / "space" / readme, BUILD / "README.md")
    shutil.copy2(ROOT / "space" / "requirements.txt", BUILD / "requirements.txt")
    shutil.copytree(
        ROOT / "tasdeeq", BUILD / "tasdeeq",
        ignore=shutil.ignore_patterns("__pycache__", "tessdata"),
    )
    # first 3 dataset invoices as demo samples (keeps the upload small);
    # staged under synth/out because app.py globs that path everywhere
    (BUILD / "synth" / "out").mkdir(parents=True)
    for d in ("0000", "0001", "0002"):
        shutil.copytree(ROOT / "synth" / "out" / d, BUILD / "synth" / "out" / d)
    if static:  # served showcase while the grant is pending
        shutil.copy2(ROOT / "docs" / "index.html", BUILD / "index.html")
        shutil.copytree(ROOT / "docs" / "assets", BUILD / "assets")

    n = sum(1 for p in BUILD.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in BUILD.rglob("*") if p.is_file())
    print(f"build/space ({'static' if static else 'gradio'}): {n} files, {size:,} bytes")


if __name__ == "__main__":
    main()
