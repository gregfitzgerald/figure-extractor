#!/usr/bin/env python3
"""
OCR-sidecar test for pdf-to-pages.py.

Generates a synthetic *scanned* (image-only, no text layer) PDF, runs the converter,
and verifies OCR recovered the caption into text.json with the per-page `ocr` flag.

Requires PyMuPDF. The OCR step needs a `tesseract` binary (found via PATH or the
FIGURE_TESSERACT_CMD env var); the test SKIPS cleanly if it isn't installed.

Run:  python3 scripts/test_ocr.py
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
CONVERTER = REPO / "scripts" / "pdf-to-pages.py"


def find_tesseract():
    return os.environ.get("FIGURE_TESSERACT_CMD") or shutil.which("tesseract")


def make_scanned_pdf(path):
    """A one-page PDF whose only content is a rasterized image -> no embedded text layer."""
    import fitz
    src = fitz.open()
    p = src.new_page(width=612, height=792)
    p.draw_rect(fitz.Rect(100, 100, 500, 400), width=1)
    p.insert_text((100, 430), "Figure 1. Scanned caption alpha beta gamma.", fontsize=13)
    pix = p.get_pixmap(matrix=fitz.Matrix(2, 2))
    scanned = fitz.open()
    sp = scanned.new_page(width=612, height=792)
    sp.insert_image(fitz.Rect(0, 0, 612, 792), pixmap=pix)
    scanned.save(path)
    scanned.close()
    src.close()


def main():
    try:
        import fitz  # noqa: F401
    except Exception as e:
        print(f"test_ocr: SKIP (missing PyMuPDF: {e})")
        return 0
    if not find_tesseract():
        print("test_ocr: SKIP (tesseract not installed)")
        return 0

    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        pdf = d / "scanned.pdf"
        make_scanned_pdf(str(pdf))
        out = d / "proj" / "Scanned"
        r = subprocess.run(
            [sys.executable, str(CONVERTER), str(pdf), str(out), "--dpi", "150"],
            capture_output=True, text=True, env=os.environ.copy(),
        )
        if r.returncode != 0:
            print("test_ocr: FAIL (converter error)\n" + r.stdout + r.stderr)
            return 1
        tj = out / "text.json"
        if not tj.exists():
            print("test_ocr: FAIL (no text.json produced)\n" + r.stdout)
            return 1
        data = json.loads(tj.read_text())
        pg = data["pages"][0]
        words = " ".join(i["str"] for i in pg["items"]).lower()
        if not (data.get("ocrPages", 0) >= 1 and pg.get("ocr") and "figure" in words and "caption" in words):
            print(f"test_ocr: FAIL (ocrPages={data.get('ocrPages')} ocr={pg.get('ocr')} words={words[:70]!r})")
            return 1

    print("test_ocr: PASS (scanned PDF -> OCR -> text.json caption recovered)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
