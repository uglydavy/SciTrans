"""Integration test for math-aware rendering (PHASE 2)."""

from pathlib import Path

import fitz

from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.dummy import DummyBackend


def test_math_aware_rendering_preserves_equations(tmp_path: Path):
    """Ensure math spans are preserved and not redacted."""
    # Create a simple math PDF
    src_pdf = tmp_path / "math.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((50, 80), "Equation: $E=mc^2$", fontsize=12)
    # Use default font for math unicode to ensure extractable text
    page.insert_text((50, 110), "Another equation: α + β = γ", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    # Run pipeline with math-aware rendering
    out_pdf = tmp_path / "out.pdf"
    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        output_dir=str(tmp_path / "outputs"),
        render_mode="math-aware",
    )
    backend = DummyBackend()

    report = run_pipeline(
        input_pdf=str(src_pdf),
        output_pdf=str(out_pdf),
        backend=backend,
        cfg=cfg,
    )

    # Verify output exists
    assert out_pdf.exists()

    # Extract text to ensure math strings remain (dummy backend returns same text)
    out_doc = fitz.open(str(out_pdf))
    text = out_doc[0].get_text()
    out_doc.close()

    assert "$E=mc^2$" in text
    # Greek letters may be substituted depending on font extraction; ensure line remains
    assert "Another equation:" in text
    assert "=" in text and "+" in text

    # Health scoring should not fail due to placeholder/math issues
    assert report["num_failed"] == 0
