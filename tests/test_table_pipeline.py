"""PHASE 4: Table preservation toggle in pipeline."""

import json
from pathlib import Path

import fitz

from scitrans.pipeline import PipelineConfig, run_pipeline
from scitrans.translation.backends.dummy import DummyBackend


def test_tables_preserved_when_not_translated(tmp_path: Path):
    src_pdf = tmp_path / "table.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((50, 80), "Normal paragraph.", fontsize=12)
    page.insert_text((50, 110), "| Col1 | Col2 |", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = tmp_path / "out.pdf"
    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        output_dir=str(tmp_path / "outputs"),
        render_mode="math-aware",
        translate_tables=False,  # preserve tables
    )

    run_pipeline(
        input_pdf=str(src_pdf),
        output_pdf=str(out_pdf),
        backend=DummyBackend(),
        cfg=cfg,
    )

    translations = json.loads((tmp_path / "outputs" / "table" / "translations.json").read_text())
    # Should contain only the normal paragraph (1 block) because table skipped
    assert len(translations) == 1

    # Renderer should keep table text intact
    out_doc = fitz.open(str(out_pdf))
    text = out_doc[0].get_text()
    out_doc.close()
    assert "| Col1 | Col2 |" in text


def test_tables_translated_when_enabled(tmp_path: Path):
    src_pdf = tmp_path / "table2.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((50, 80), "Normal paragraph.", fontsize=12)
    page.insert_text((50, 110), "| Col1 | Col2 |", fontsize=12)
    doc.save(str(src_pdf))
    doc.close()

    out_pdf = tmp_path / "out.pdf"
    cfg = PipelineConfig(
        source_lang="en",
        target_lang="fr",
        output_dir=str(tmp_path / "outputs"),
        render_mode="math-aware",
        translate_tables=True,  # translate tables
    )

    run_pipeline(
        input_pdf=str(src_pdf),
        output_pdf=str(out_pdf),
        backend=DummyBackend(),
        cfg=cfg,
    )

    translations = json.loads((tmp_path / "outputs" / "table2" / "translations.json").read_text())
    # Should contain both blocks (2) because tables allowed
    assert len(translations) == 2

    # Renderer should reinsert table content (dummy backend is identity)
    out_doc = fitz.open(str(out_pdf))
    text = out_doc[0].get_text()
    out_doc.close()
    assert "| Col1 | Col2 |" in text
