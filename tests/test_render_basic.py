from pathlib import Path

import fitz

from scitrans.parsing.pymupdf_parser import parse_pdf
from scitrans.rendering.math_safe_renderer import render_translated_pdf


def test_render_basic(tmp_path: Path):
    # Create a simple PDF
    src_pdf = tmp_path / "src.pdf"
    doc = fitz.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((50, 80), "Hello world", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    parsed = parse_pdf(str(src_pdf))
    # Build translations: replace all text blocks with French
    translations = {}
    for p in parsed.pages:
        for b in p.blocks:
            if b.type == "text":
                translations[b.id] = "Bonjour le monde"

    out_pdf = tmp_path / "out.pdf"
    render_translated_pdf(
        source_pdf=str(src_pdf), doc=parsed, translations=translations, output_pdf=str(out_pdf)
    )

    # Verify output exists and contains translated text
    out = fitz.open(str(out_pdf))
    text = out[0].get_text()
    out.close()
    assert "Bonjour le monde" in text
