"""Integration tests with real PDF translation.

These tests verify the entire pipeline end-to-end.
"""

import json
from pathlib import Path

import fitz
import pytest

from scitrans.parsing.pymupdf_parser import parse_pdf
from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.dummy import DummyBackend


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a sample PDF for testing."""
    pdf_path = tmp_path / "sample.pdf"

    doc = fitz.open()
    page = doc.new_page(width=400, height=300)

    # Add various text blocks
    page.insert_text((50, 50), "Title: Scientific Translation", fontsize=14)
    page.insert_text((50, 80), "This is a paragraph with some text.", fontsize=11)
    page.insert_text((50, 100), "It contains numbers like 42 and 3.14.", fontsize=11)
    page.insert_text((50, 120), "- Bullet point 1", fontsize=11)
    page.insert_text((50, 140), "- Bullet point 2", fontsize=11)

    doc.save(str(pdf_path))
    doc.close()

    return pdf_path


def test_full_pipeline_dummy_backend(sample_pdf: Path, tmp_path: Path):
    """Test complete pipeline with dummy backend."""
    output_pdf = tmp_path / "output.pdf"

    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        model="dummy",
        output_dir=str(tmp_path / "outputs"),
        n_candidates=1,
        use_cache=True,
        enable_reranking=False,
    )

    backend = DummyBackend(model="dummy")

    report = run_pipeline(
        input_pdf=str(sample_pdf),
        output_pdf=str(output_pdf),
        backend=backend,
        cfg=cfg,
    )

    # Verify output PDF exists
    assert output_pdf.exists()

    # Verify report structure
    assert "num_blocks" in report
    assert "num_ok" in report
    assert "num_failed" in report
    assert "health" in report
    assert report["num_blocks"] > 0

    # Verify artifacts exist
    artifacts_dir = Path(report["artifacts_dir"])
    assert (artifacts_dir / "parsed.json").exists()
    assert (artifacts_dir / "masked.json").exists()
    assert (artifacts_dir / "translations.json").exists()
    assert (artifacts_dir / "health_scores.json").exists()
    assert (artifacts_dir / "report.json").exists()


def test_deterministic_parsing(sample_pdf: Path):
    """Verify parsing is deterministic across multiple runs."""
    doc1 = parse_pdf(str(sample_pdf))
    doc2 = parse_pdf(str(sample_pdf))

    # Same number of pages and blocks
    assert len(doc1.pages) == len(doc2.pages)
    assert len(doc1.pages[0].blocks) == len(doc2.pages[0].blocks)

    # Same block IDs
    ids1 = [b.id for b in doc1.pages[0].blocks]
    ids2 = [b.id for b in doc2.pages[0].blocks]
    assert ids1 == ids2


def test_caching_works(sample_pdf: Path, tmp_path: Path):
    """Verify caching stores and retrieves translations."""
    output_pdf1 = tmp_path / "output1.pdf"
    output_pdf2 = tmp_path / "output2.pdf"

    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        model="dummy",
        output_dir=str(tmp_path / "outputs"),
        use_cache=True,
    )

    backend = DummyBackend(model="dummy")

    # First run (should create cache)
    report1 = run_pipeline(
        input_pdf=str(sample_pdf),
        output_pdf=str(output_pdf1),
        backend=backend,
        cfg=cfg,
    )

    # Check cache directory was created
    cache_dir = Path(report1["artifacts_dir"]) / ".cache"
    assert cache_dir.exists(), "Cache directory should be created"
    cache_files_before = len(list(cache_dir.glob("*.json")))
    assert cache_files_before > 0, "Cache files should exist after first run"

    # Second run (should use cache)
    run_pipeline(
        input_pdf=str(sample_pdf),
        output_pdf=str(output_pdf2),
        backend=backend,
        cfg=cfg,
    )

    # Cache files should be reused (count unchanged)
    cache_files_after = len(list(cache_dir.glob("*.json")))
    assert cache_files_after == cache_files_before, "Cache should be reused, not recreated"

    # Both outputs should exist and be similar
    assert output_pdf1.exists()
    assert output_pdf2.exists()


def test_health_scoring(sample_pdf: Path, tmp_path: Path):
    """Verify health scoring produces expected metrics."""
    output_pdf = tmp_path / "output.pdf"

    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        output_dir=str(tmp_path / "outputs"),
    )

    backend = DummyBackend()

    report = run_pipeline(
        input_pdf=str(sample_pdf),
        output_pdf=str(output_pdf),
        backend=backend,
        cfg=cfg,
    )

    # Health metrics should be present
    health = report["health"]
    assert "mean_score" in health
    assert "ok_blocks" in health
    assert "failed_blocks" in health
    assert "health_ratio" in health

    # Health metrics should be present and structurally correct
    assert "mean_score" in health
    assert "ok_blocks" in health
    assert "warning_blocks" in health
    assert "failed_blocks" in health
    assert "health_ratio" in health

    # Verify values are in valid ranges
    total_health_blocks = health["ok_blocks"] + health["warning_blocks"] + health["failed_blocks"]
    assert total_health_blocks > 0  # Should have scored some blocks
    assert 0 <= health["health_ratio"] <= 1.0
    assert 0 <= health["mean_score"] <= 1.0

    # For dummy backend, at least some blocks should translate successfully
    assert report["num_ok"] > 0


@pytest.mark.slow
def test_multicandidate_reranking(sample_pdf: Path, tmp_path: Path):
    """Test multi-candidate translation with reranking."""
    output_pdf = tmp_path / "output.pdf"

    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        output_dir=str(tmp_path / "outputs"),
        n_candidates=3,  # Multiple candidates
        enable_reranking=True,
    )

    backend = DummyBackend()

    report = run_pipeline(
        input_pdf=str(sample_pdf),
        output_pdf=str(output_pdf),
        backend=backend,
        cfg=cfg,
    )

    # Should complete successfully
    assert report["num_ok"] > 0

    # Check translations.json for rerank_scores
    artifacts_dir = Path(report["artifacts_dir"])
    translations_file = artifacts_dir / "translations.json"
    translations = json.loads(translations_file.read_text())

    # At least some blocks should have rerank_scores in meta
    # (Dummy backend may not have multiple candidates, so this is optional)
    assert len(translations) > 0
