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
import json
import os
import sys
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("Error: PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)


def convert_pdf(pdf_path: str, output_dir: str = None, dpi: int = 150):
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
    
    print(f"Converting: {pdf_path.name}")
    print(f"Output dir: {output_dir}")
    print(f"DPI: {dpi}")
    print()
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    scale = dpi / 72  # PDF default is 72 DPI
    
    for i, page in enumerate(doc):
        page_num = i + 1
        filename = f"{page_num:04d}.png"
        output_path = output_dir / filename
        
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat)
        pix.save(str(output_path))
        
        size_kb = output_path.stat().st_size / 1024
        print(f"  {filename} ({pix.width}x{pix.height}, {size_kb:.0f} KB)")
    
    doc.close()
    
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
    print(f"✓ Ready for Figure Extractor: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF to numbered PNG pages for Figure Extractor"
    )
    parser.add_argument("pdf", help="Input PDF file")
    parser.add_argument("output", nargs="?", help="Output directory (default: PDF name)")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for conversion (default: 150)")
    
    args = parser.parse_args()
    convert_pdf(args.pdf, args.output, args.dpi)


if __name__ == "__main__":
    main()
