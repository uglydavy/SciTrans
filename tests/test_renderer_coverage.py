"""Regression tests for renderer coverage / preservation.

These tests protect against a critical failure mode:

- The pipeline may intentionally skip translating some blocks (e.g., tables when
  translate_tables=False).
- Or a translation may fail for some blocks (empty output).

In those cases the renderer MUST NOT redact the original content without replacing
it, otherwise headers/tables/etc disappear from the output PDF.
"""

from __future__ import annotations

from dataclasses import dataclass
import pytest
from pathlib import Path

import fitz
import pytest

from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.base import TranslateRequest, TranslateResult


@dataclass
class PrefixBackend:
    """A deterministic test backend that prefixes text to simulate real translation."""

    name: str = "prefix"
    model: str = "prefix"

    def translate(self, req: TranslateRequest) -> TranslateResult:
        return TranslateResult(
            candidates=[f"FR: {req.text}"],
            model=self.model,
            backend=self.name,
            meta={},
        )


@dataclass
class EmptyOnKeywordBackend:
    """Backend that returns empty translation for blocks containing a keyword."""

    keyword: str
    name: str = "empty-on-keyword"
    model: str = "empty-on-keyword"

    def translate(self, req: TranslateRequest) -> TranslateResult:
        if self.keyword.lower() in req.text.lower():
            cands = [""]
        else:
            cands = [f"FR: {req.text}"]
        return TranslateResult(candidates=cands, model=self.model, backend=self.name, meta={})


@pytest.mark.parametrize("render_mode", ["perfect", "enhanced"])
def test_renderer_preserves_untranslated_tables(tmp_path: Path, render_mode: str):
    """When translate_tables=False, table blocks must remain visible in output."""

    input_pdf = Path(__file__).resolve().parents[1] / "test_pdfs" / "04_tables.pdf"
    # Skip this test if the test PDF is not available
    if not input_pdf.exists():
        pytest.skip(f"Missing test PDF: {input_pdf}")

    output_pdf = tmp_path / f"out_{render_mode}.pdf"

    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        model="prefix",
        output_dir=str(tmp_path / "artifacts"),
        n_candidates=1,
        use_cache=False,
        enable_reranking=False,
        translate_tables=False,
        render_mode=render_mode,
    )

    report = run_pipeline(
        input_pdf=str(input_pdf),
        output_pdf=str(output_pdf),
        backend=PrefixBackend(),
        cfg=cfg,
    )

    assert output_pdf.exists(), "Renderer should produce an output PDF"
    assert report["num_blocks"] > 0

    # Table content MUST still be present (we're preserving tables, not translating them)
    out_doc = fitz.open(str(output_pdf))
    out_text = out_doc[0].get_text()
    out_doc.close()

    # A few strings that are part of the table (see test_pdfs/04_tables.pdf)
    assert "Baseline" in out_text
    assert "Proposed" in out_text
    assert "Advanced" in out_text

    # And at least one non-table paragraph should have been "translated" (prefixed)
    assert "FR:" in out_text


def test_perfect_renderer_does_not_blank_on_empty_translation(tmp_path: Path):
    """If a backend returns an empty translation, the original text must remain."""

    input_pdf = Path(__file__).resolve().parents[1] / "test_pdfs" / "01_simple_text.pdf"
    if not input_pdf.exists():
        pytest.skip(f"Missing test PDF: {input_pdf}")

    output_pdf = tmp_path / "out_empty_translation.pdf"

    # We will force an empty translation for blocks containing 'Simple'
    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        model="empty",
        output_dir=str(tmp_path / "artifacts"),
        n_candidates=1,
        use_cache=False,
        enable_reranking=False,
        translate_tables=False,
        render_mode="perfect",
    )

    report = run_pipeline(
        input_pdf=str(input_pdf),
        output_pdf=str(output_pdf),
        backend=EmptyOnKeywordBackend(keyword="Simple"),
        cfg=cfg,
    )

    assert output_pdf.exists()
    assert report["num_blocks"] > 0

    out_doc = fitz.open(str(output_pdf))
    out_text = out_doc[0].get_text()
    out_doc.close()

    # The original title contains the word "Simple"; it must still be present
    # even if its translation was empty.
    assert "simple test document" in out_text.lower()
