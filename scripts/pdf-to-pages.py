#!/usr/bin/env python3
"""
Convert PDF to numbered PNG pages for the Figure Extractor tool.

Usage:
    python pdf-to-pages.py <input.pdf> [output_dir] [--dpi 150]

Output:
    output_dir/
        0001.png
        0002.png
        ...
        metadata.json  (page count, DPI, source file)

If output_dir is not specified, creates a directory named after the PDF.
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)


def find_tesseract():
    """Locate the tesseract binary (env override wins), or None if unavailable."""
    return os.environ.get("FIGURE_TESSERACT_CMD") or shutil.which("tesseract")


def ocr_words(png_path, tesseract, min_conf=40):
    """OCR a rendered page image -> word items {str,x,y,w,h} in the image's natural pixels.

    Tesseract runs on the rendered PNG, so its coordinates already match the PNG pixel
    space the tool uses -- no scaling needed. Returns [] on any failure.
    """
    try:
        out = subprocess.run(
            [tesseract, str(png_path), "stdout", "--psm", "3", "tsv"],
            capture_output=True, text=True, timeout=180,
        )
    except Exception:
        return []
    items = []
    for row in csv.DictReader(out.stdout.splitlines(), delimiter="\t"):
        text = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf", "-1"))
        except (TypeError, ValueError):
            continue
        if text and conf >= min_conf:
            items.append({
                "str": text + " ",
                "x": float(row["left"]), "y": float(row["top"]),
                "w": float(row["width"]), "h": float(row["height"]),
            })
    return items


def convert_pdf(pdf_path: str, output_dir: str = None, dpi: int = 150, use_ocr: bool = True):
    """Convert PDF to numbered PNG pages."""

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}")
        sys.exit(1)

    # Default output directory: same name as PDF (without extension)
    if output_dir is None:
        output_dir = pdf_path.parent / pdf_path.stem
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    tesseract = find_tesseract() if use_ocr else None

    print(f"Converting: {pdf_path.name}")
    print(f"Output dir: {output_dir}")
    print(f"DPI: {dpi}")
    if use_ocr:
        print(f"OCR fallback: {'tesseract (' + tesseract + ')' if tesseract else 'unavailable (install tesseract-ocr)'}")
    print()

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    scale = dpi / 72  # PDF default is 72 DPI

    text_pages = []  # sidecar text layer, mapped into PNG natural pixels
    ocr_page_count = 0

    for i, page in enumerate(doc):
        page_num = i + 1
        filename = f"{page_num:04d}.png"
        output_path = output_dir / filename

        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(output_path))

        size_kb = output_path.stat().st_size / 1024

        # Extract the text layer as words, scaled to match the rendered PNG (natural px).
        # This lets the browser tool auto-associate captions for folder-based projects
        # (which have no in-browser PDF text layer). Same {str,x,y,w,h} shape the tool uses.
        items = []
        for x0, y0, x1, y1, word, *_ in page.get_text("words"):
            if not word.strip():
                continue
            items.append({
                # trailing space: PyMuPDF returns word tokens with no space glyphs, so the
                # browser reconstructs inter-word spacing from this rather than from gaps.
                "str": word + " ",
                "x": round(x0 * scale, 1),
                "y": round(y0 * scale, 1),
                "w": round((x1 - x0) * scale, 1),
                "h": round((y1 - y0) * scale, 1),
            })

        # No embedded text (scanned page): fall back to OCR on the rendered image.
        page_ocr = False
        if not items and tesseract:
            items = ocr_words(output_path, tesseract)
            if items:
                page_ocr = True
                ocr_page_count += 1

        note = " [OCR]" if page_ocr else ""
        print(f"  {filename} ({pix.width}x{pix.height}, {size_kb:.0f} KB){note}")
        text_pages.append({"pageNum": page_num, "width": pix.width, "height": pix.height,
                           "items": items, "ocr": page_ocr})

    doc.close()

    # Write text sidecar (skip if the PDF has no extractable text layer, e.g. scanned)
    total_words = sum(len(p["items"]) for p in text_pages)
    if total_words:
        text_path = output_dir / "text.json"
        with open(text_path, "w") as f:
            json.dump({"schemaVersion": 1, "source": pdf_path.name, "dpi": dpi,
                       "ocrPages": ocr_page_count, "pages": text_pages}, f)
        tail = f" ({ocr_page_count} via OCR)" if ocr_page_count else ""
        print(f"  text.json ({total_words} words across {total_pages} pages){tail}")
    
    # Write metadata
    metadata = {
        "source": pdf_path.name,
        "pages": total_pages,
        "dpi": dpi,
        "width": pix.width,
        "height": pix.height
    }
    
    metadata_path = output_dir / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print()
    print(f"✓ Converted {total_pages} pages")
    print(f"✓ Metadata saved to metadata.json")
    if total_words:
        via = f" ({ocr_page_count} page(s) via OCR)" if ocr_page_count else ""
        print(f"✓ Text layer saved to text.json (captions will auto-detect){via}")
    elif use_ocr and not tesseract:
        print(f"  No text layer found and tesseract not installed — captions must be typed manually")
        print(f"  (install with: sudo apt-get install tesseract-ocr)")
    else:
        print(f"  No text layer found (blank/scanned PDF?) — captions must be typed manually")
    print(f"✓ Ready for Figure Extractor: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to numbered PNG pages for Figure Extractor"
    )
    parser.add_argument("pdf", help="Input PDF file")
    parser.add_argument("output", nargs="?", help="Output directory (default: PDF name)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for conversion (default: 150)")
    parser.add_argument("--no-ocr", action="store_true",
                        help="Disable OCR fallback for scanned pages (default: OCR if tesseract is installed)")

    args = parser.parse_args()
    convert_pdf(args.pdf, args.output, args.dpi, use_ocr=not args.no_ocr)


if __name__ == "__main__":
    main()
