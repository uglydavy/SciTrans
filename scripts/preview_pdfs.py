#!/usr/bin/env python3
"""PDF preview and comparison tool.

Generates side-by-side PNG previews of source and translated PDFs.
"""

import argparse
import sys
from pathlib import Path


def create_preview(pdf_path: str, output_path: str, page: int = 0, dpi: int = 150):
    """Create PNG preview of PDF page."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("Error: PyMuPDF not installed. Run: pip install pymupdf")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    if page >= len(doc):
        print(f"Error: Page {page} not found (PDF has {len(doc)} pages)")
        doc.close()
        sys.exit(1)

    page_obj = doc[page]
    # Render at specified DPI
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page_obj.get_pixmap(matrix=mat)
    pix.save(output_path)
    doc.close()

    return output_path


def create_side_by_side(
    source_pdf: str, translated_pdf: str, output_dir: str = "previews", page: int = 0
):
    """Create side-by-side comparison of source and translated PDFs."""
    try:
        from PIL import Image
    except ImportError:
        print("Error: Pillow not installed. Run: pip install pillow")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # Create individual previews
    print(f"Generating preview for page {page}...")
    source_png = output_path / f"source_page_{page}.png"
    translated_png = output_path / f"translated_page_{page}.png"

    create_preview(source_pdf, str(source_png), page=page)
    create_preview(translated_pdf, str(translated_png), page=page)

    # Create side-by-side comparison
    source_img = Image.open(source_png)
    translated_img = Image.open(translated_png)

    # Ensure same height
    if source_img.height != translated_img.height:
        # Resize to match heights
        target_height = max(source_img.height, translated_img.height)
        if source_img.height < target_height:
            ratio = target_height / source_img.height
            source_img = source_img.resize(
                (int(source_img.width * ratio), target_height), Image.Resampling.LANCZOS
            )
        if translated_img.height < target_height:
            ratio = target_height / translated_img.height
            translated_img = translated_img.resize(
                (int(translated_img.width * ratio), target_height), Image.Resampling.LANCZOS
            )

    # Create combined image
    total_width = source_img.width + translated_img.width + 20  # 20px gap
    combined = Image.new("RGB", (total_width, source_img.height), "white")

    # Paste images
    combined.paste(source_img, (0, 0))
    combined.paste(translated_img, (source_img.width + 20, 0))

    # Save comparison
    comparison_path = output_path / f"comparison_page_{page}.png"
    combined.save(comparison_path)

    print(f"✓ Source preview: {source_png}")
    print(f"✓ Translated preview: {translated_png}")
    print(f"✓ Side-by-side comparison: {comparison_path}")

    return comparison_path


def create_all_pages(source_pdf: str, translated_pdf: str, output_dir: str = "previews"):
    """Create previews for all pages."""
    try:
        import fitz
    except ImportError:
        print("Error: PyMuPDF not installed. Run: pip install pymupdf")
        sys.exit(1)

    doc = fitz.open(source_pdf)
    num_pages = len(doc)
    doc.close()

    print(f"Generating previews for {num_pages} pages...")

    for page in range(num_pages):
        print(f"\nPage {page + 1}/{num_pages}:")
        create_side_by_side(source_pdf, translated_pdf, output_dir, page)

    print(f"\n✓ All previews saved to: {output_dir}/")


def main():
    parser = argparse.ArgumentParser(
        description="Generate PDF previews and side-by-side comparisons"
    )
    parser.add_argument("--source", required=True, help="Source PDF path")
    parser.add_argument("--translated", required=True, help="Translated PDF path")
    parser.add_argument("--output", default="previews", help="Output directory (default: previews)")
    parser.add_argument("--page", type=int, help="Specific page number (0-indexed)")
    parser.add_argument("--all", action="store_true", help="Generate previews for all pages")

    args = parser.parse_args()

    if args.all:
        create_all_pages(args.source, args.translated, args.output)
    elif args.page is not None:
        create_side_by_side(args.source, args.translated, args.output, args.page)
    else:
        # Default: first page
        create_side_by_side(args.source, args.translated, args.output, 0)


if __name__ == "__main__":
    main()
