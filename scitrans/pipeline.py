from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from scitrans.core.models import Document, MaskedBlock, TranslatedBlock
from scitrans.masking.engine import MaskingEngine
from scitrans.metrics.health import compute_block_health, compute_page_health
from scitrans.metrics.layout import compute_block_overlap_metrics
from scitrans.metrics.scoring import (
    aggregate_scores,
    compute_post_translation_score,
    compute_pre_translation_score,
)
from scitrans.parsing.pymupdf_parser import parse_pdf
from scitrans.rendering.enhanced_block_renderer import render_translated_pdf_enhanced
from scitrans.rendering.math_aware_renderer import (
    MathAwareRenderConfig,
    render_translated_pdf_math_aware,
)
from scitrans.rendering.math_safe_renderer import RenderConfig, render_translated_pdf
from scitrans.rendering.perfect_renderer import render_translated_pdf_perfect
from scitrans.translation.backends.base import TranslateRequest, TranslationBackend
from scitrans.translation.cache import TranslationCache, make_cache_key
from scitrans.translation.prompting import build_system_prompt
from scitrans.translation.reranking import rerank_candidates

# Import glossary system
try:
    from scitrans.translation.glossary.manager import GlossaryManager
except ImportError:
    GlossaryManager = None  # type: ignore

console = Console()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineConfig:
    source_lang: str = "en"
    target_lang: str = "fr"
    model: str = "dummy"
    temperature: float = 0.0
    n_candidates: int = 1
    output_dir: str = "outputs"
    assets_dir: Optional[str] = None  # fonts etc
    render: RenderConfig = RenderConfig()
    # Renderer mode: "perfect" (100% perfection), "enhanced" (preserves major styling), "auto" (detect math), "math-aware", "math-safe" (legacy)
    render_mode: str = "perfect"  # Default: perfect rendering with exact font sizes
    translate_tables: bool = False  # PHASE 4: default preserve tables
    # Phase 3 features
    use_cache: bool = False  # Default to False - always translate fresh
    context_window: int = 0  # Number of previous blocks to include as context
    enable_reranking: bool = True
    retry_failed: bool = True  # Retry failed blocks with stronger constraints
    # Coverage guarantee features (from old repo)
    max_translation_retries: int = 2  # Retry failed blocks this many times
    detect_identity_translation: bool = True  # Detect when output == input
    # Glossary features
    glossary_domains: Optional[list[str]] = None  # Domains to load (e.g., ["ml", "physics"])
    # Performance features
    parallel_translation: bool = False  # Enable parallel block translation (experimental)
    max_workers: int = 4  # Max parallel workers for translation


def _block_text(block) -> str:
    # Preserve line breaks from PDF extraction.
    lines = []
    for ln in block.lines:
        lines.append("".join(sp.text for sp in ln.spans))
    return "\n".join(lines).strip("\n")


def run_pipeline(
    *,
    input_pdf: str,
    output_pdf: str,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    glossary: Optional[dict[str, str]] = None,
) -> dict:
    t0 = time.time()
    logger.info(f"Starting translation pipeline: {input_pdf} -> {output_pdf}")
    logger.debug(f"Backend: {backend.name}, Config: {cfg}")
    out_dir = Path(cfg.output_dir) / Path(input_pdf).stem
    
    # Clear all previous artifacts and cache for this PDF to ensure fresh translation
    if out_dir.exists():
        logger.info(f"Clearing previous artifacts for {Path(input_pdf).stem}")
        import shutil
        try:
            shutil.rmtree(out_dir)
            logger.info("Cleared previous artifacts")
        except Exception as e:
            logger.warning(f"Could not fully clear artifacts: {e}")
    
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Artifacts directory: {out_dir}")

    # 1) Parse
    logger.info(f"Parsing PDF: {input_pdf}")
    doc = parse_pdf(input_pdf)
    logger.debug(f"Parsed {len(doc.pages)} pages, {sum(len(p.blocks) for p in doc.pages)} blocks")
    (out_dir / "parsed.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    # 2) Mask
    masker = MaskingEngine()
    masked_blocks: list[MaskedBlock] = []
    for page in doc.pages:
        for block in page.blocks:
            if block.type != "text":
                continue
            # PHASE 4: Preserve tables unless explicitly translating
            if block.meta.get("region") == "table" and not cfg.translate_tables:
                continue
            src = _block_text(block)
            # Skip empty blocks
            if not src.strip():
                continue
            masked, registry, counts = masker.mask(src)
            masked_blocks.append(
                MaskedBlock(
                    block_id=block.id, masked_text=masked, registry=registry, mask_counts=counts
                )
            )
    logger.info(f"Masked {len(masked_blocks)} blocks for translation (all text blocks included)")
    (out_dir / "masked.json").write_text(
        json.dumps([mb.model_dump() for mb in masked_blocks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 2.5) Pre-translation scoring
    console.print("[cyan]Computing pre-translation complexity scores...[/cyan]")
    pre_scores = []
    for mb in masked_blocks:
        # Get original source text
        source_text = ""
        for page in doc.pages:
            for block in page.blocks:
                if block.id == mb.block_id:
                    source_text = _block_text(block)
                    break
        pre_score = compute_pre_translation_score(mb.block_id, source_text)
        pre_scores.append(pre_score)

    (out_dir / "pre_scores.json").write_text(
        json.dumps([s.__dict__ for s in pre_scores], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"[green]✓ Pre-scored {len(pre_scores)} blocks[/green]")

    # 2.7) Load domain glossaries if specified
    if cfg.glossary_domains and GlossaryManager:
        try:
            glossary_mgr = GlossaryManager()
            for domain in cfg.glossary_domains:
                loaded_count = glossary_mgr.load_domain(
                    domain, f"{cfg.source_lang}-{cfg.target_lang}"
                )
                if loaded_count > 0:
                    console.print(
                        f"[green]✓ Loaded {loaded_count} terms from {domain} glossary[/green]"
                    )

            # Merge with user glossary
            if glossary:
                glossary_mgr.add_custom_terms(glossary)

            # Get combined glossary
            glossary = glossary_mgr.get_glossary_dict()
            console.print(f"[green]✓ Total glossary terms: {len(glossary)}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Could not load domain glossaries: {e}[/yellow]")

    # 3) Translate - NO CACHING, always fresh translation
    system_prompt = build_system_prompt(
        source=cfg.source_lang, target=cfg.target_lang, glossary=glossary
    )
    # ALWAYS disable cache to ensure fresh translations
    cache = None
    translation_memory = None
    logger.info("Cache and translation memory disabled - translating all blocks fresh")

    translated_blocks: list[TranslatedBlock] = []
    translations: dict[str, str] = {}
    # NO CONTEXT BUFFER - user doesn't care about context retention
    pre_scores_by_id = {s.block_id: s for s in pre_scores}

    for mb in masked_blocks:  # Get pre-score for adaptive strategy
        pre_score = pre_scores_by_id.get(mb.block_id)

        # Adapt parameters based on complexity
        if pre_score and pre_score.is_complex():
            # Complex block: use recommended settings
            block_n_candidates = pre_score.recommended_candidates
            block_temperature = pre_score.recommended_temperature
            console.print(
                f"[yellow]Complex block {mb.block_id}: using {block_n_candidates} candidates, temp={block_temperature}[/yellow]"
            )
        else:
            # Normal block: use config settings
            block_n_candidates = cfg.n_candidates
            block_temperature = cfg.temperature

        # NO CACHE, NO MEMORY - Always translate fresh
        cache_key = None
        cached_result = None
        memory_match = None

        candidates: list[str] = []
        res_meta: dict = {}
        
        # Always translate - no cache, no memory, no context
        # Translate each block independently
        req = TranslateRequest(
            text=mb.masked_text,
            source_lang=cfg.source_lang,
            target_lang=cfg.target_lang,
            system_prompt=system_prompt,
            temperature=block_temperature,
            n_candidates=block_n_candidates,
            context="",  # No context - user doesn't care about context retention
        )

        # DEBUG: Log what we're sending to backend
        masked_preview = mb.masked_text[:80] + "..." if len(mb.masked_text) > 80 else mb.masked_text
        logger.info(f"Block {mb.block_id}: Sending to backend (masked): {masked_preview}")
        if idx < 3:  # Log first 3 blocks
            console.print(f"[cyan]📤 Block {mb.block_id}: Sending '{masked_preview}' to backend[/cyan]")
        
        try:
            res = backend.translate(req)
            candidates = res.candidates if res.candidates else [""]
            res_meta = {
                "backend": backend.name,
                "model": getattr(backend, "model", cfg.model),
                "cached": False,
                **res.meta,
            }

            # DEBUG: Log what we got back from backend
            if candidates and candidates[0]:
                candidate_preview = candidates[0][:100] + "..." if len(candidates[0]) > 100 else candidates[0]
                logger.info(f"Block {mb.block_id}: Backend returned {len(candidates[0])} chars: {candidate_preview}")
                console.print(f"[cyan]Block {mb.block_id}: Backend returned: {candidate_preview}[/cyan]")
            else:
                logger.warning(f"Block {mb.block_id}: Backend returned EMPTY translation!")
                console.print(f"[red]Block {mb.block_id}: Backend returned EMPTY![/red]")

            # Log which backends were used (for cascade_free)
            if backend.name == "cascade_free" and res.meta.get("backends_used"):
                backend_names = [
                    b["backend"] for b in res.meta["backends_used"] if b.get("success")
                ]
                if backend_names:
                    logger.info(
                        f"Block {mb.block_id}: cascade_free used {', '.join(backend_names)}"
                    )
                    console.print(
                        f"[cyan]Block {mb.block_id}: Using {', '.join(backend_names)}[/cyan]"
                    )
                    # Warn if only Google Translate
                    if backend_names == ["google"]:
                        console.print(
                            f"[yellow]⚠ Block {mb.block_id}: Using Google Translate only - quality may be poor[/yellow]"
                        )
                else:
                    logger.error(f"Block {mb.block_id}: cascade_free - NO backends succeeded!")
                    console.print(
                        f"[red]❌ Block {mb.block_id}: All backends failed![/red]"
                    )
        except Exception as e:
            logger.error(f"Block {mb.block_id}: Backend translation failed: {e}", exc_info=True)
            candidates = [""]
            res_meta = {
                "backend": backend.name,
                "model": getattr(backend, "model", cfg.model),
                "cached": False,
                "error": str(e),
            }
            console.print(f"[red]❌ Block {mb.block_id}: Translation error: {e}[/red]")
        # NO CACHING - Don't store results

        # Rerank candidates if enabled and multiple candidates
        if cfg.enable_reranking and len(candidates) > 1:
            # Get source text for reranking (unmasked)
            source_text = mb.masked_text
            # Find original source text from document
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text = _block_text(block)
                        break

            ranked = rerank_candidates(
                candidates=candidates,
                source_text=source_text,
                registry=mb.registry,
                glossary=glossary,
            )
            if ranked:
                # Log which candidate was selected
                if len(ranked) > 1:
                    logger.debug(
                        f"Block {mb.block_id}: Reranked {len(ranked)} candidates, "
                        f"best score: {ranked[0][1].total:.2f} (valid: {ranked[0][1].is_valid()})"
                    )
                candidates = [c for c, _ in ranked]
                res_meta["rerank_scores"] = {
                    "best_score": ranked[0][1].total,
                    "best_valid": ranked[0][1].is_valid(),
                    "num_candidates_ranked": len(ranked),
                }

        # Validate BEFORE restoration: placeholder preservation is a hard gate
        candidate = candidates[0] if candidates else ""
        placeholders_ok = candidate.strip() != "" and masker.placeholders_present(
            candidate, mb.registry
        )

        # Restore placeholders
        restored, restore_errors = masker.restore(candidate, mb.registry, tolerant=True)

        # DEBUG: Log restored text
        if restored:
            restored_preview = restored[:100] + "..." if len(restored) > 100 else restored
            logger.info(f"Block {mb.block_id}: After restore: {len(restored)} chars: {restored_preview}")
        else:
            logger.warning(f"Block {mb.block_id}: After restore: EMPTY!")

        # Check for identity translation (output == input)
        identity_translation = False
        if cfg.detect_identity_translation and restored.strip():
            # Get original source text for comparison
            source_text_for_check = ""
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text_for_check = _block_text(block)
                        break

            # Compare (case-insensitive, whitespace-normalized)
            if restored.strip().lower() == source_text_for_check.strip().lower():
                identity_translation = True
                console.print(
                    f"[red]⚠⚠⚠ IDENTITY TRANSLATION DETECTED for block {mb.block_id} - Backend returned source text unchanged![/red]"
                )
                logger.error(
                    f"Block {mb.block_id}: Identity translation! Source: '{source_text_for_check[:50]}...' == Restored: '{restored[:50]}...'"
                )
                restore_errors.append("identity_translation")

        # Overall validation
        # A block is OK only if:
        # 1. Placeholders are preserved
        # 2. No restore errors
        # 3. Not an identity translation (output != input)
        # 4. Translation is not empty
        ok = (
            placeholders_ok 
            and len(restore_errors) == 0 
            and not identity_translation
            and restored.strip() != ""
        )

        # Retry with stronger constraints if failed and retry enabled
        # Only retry if:
        # 1. Not cached (cached results shouldn't be retried)
        # 2. Backend actually returned something (not empty)
        # 3. Either placeholders missing OR identity translation detected
        should_retry = (
            not ok 
            and cfg.retry_failed 
            and not cached_result
            and candidate.strip() != ""  # Backend returned something
            and (not placeholders_ok or identity_translation)  # Only retry for these specific failures
        )
        
        if should_retry:
            console.print(
                f"[yellow]Retrying block {mb.block_id} with stronger constraints[/yellow]"
            )
            # Retry with lower temperature and explicit translation instruction
            retry_prompt = (
                system_prompt
                + "\n\nCRITICAL: You MUST translate the text to the target language. "
                + "Do NOT return the source text unchanged. "
                + "You MUST preserve ALL placeholders exactly as written."
            )
            retry_req = TranslateRequest(
                text=mb.masked_text,
                source_lang=cfg.source_lang,
                target_lang=cfg.target_lang,
                system_prompt=retry_prompt,
                temperature=max(0.0, cfg.temperature - 0.2),
                n_candidates=1,
            )
            try:
                retry_res = backend.translate(retry_req)
                retry_candidate = retry_res.candidates[0] if retry_res.candidates else ""

                # Only proceed if retry returned something
                if retry_candidate.strip():
                    # Validate BEFORE restoration
                    retry_placeholders_ok = masker.placeholders_present(retry_candidate, mb.registry)
                    retry_restored, retry_restore_errors = masker.restore(
                        retry_candidate, mb.registry, tolerant=True
                    )
                    
                    # Check for identity translation again after retry
                    retry_identity = False
                    if cfg.detect_identity_translation and retry_restored.strip():
                        source_text_for_check = ""
                        for page in doc.pages:
                            for block in page.blocks:
                                if block.id == mb.block_id:
                                    source_text_for_check = _block_text(block)
                                    break
                        if retry_restored.strip().lower() == source_text_for_check.strip().lower():
                            retry_identity = True
                            retry_restore_errors.append("identity_translation")
                    
                    retry_ok = retry_placeholders_ok and len(retry_restore_errors) == 0 and not retry_identity
                    if retry_ok:
                        candidate = retry_candidate
                        restored = retry_restored
                        restore_errors = retry_restore_errors
                        ok = True
                        res_meta["retried"] = True
            except Exception as e:
                logger.debug(f"Retry failed for block {mb.block_id}: {e}")
                pass  # Keep original failed result

        translated_blocks.append(
            TranslatedBlock(
                block_id=mb.block_id,
                source_text=mb.masked_text,
                translated_text=restored,
                ok=ok,
                errors=restore_errors if restore_errors else ([] if ok else ["validation_failed"]),
                meta=res_meta,
            )
        )
        translations[mb.block_id] = restored
        
        # DEBUG: Log final translation status
        if ok:
            logger.info(f"Block {mb.block_id}: ✅ OK - Translation stored")
        else:
            logger.error(f"Block {mb.block_id}: ❌ FAILED - Errors: {restore_errors if restore_errors else ['validation_failed']}")
            if identity_translation:
                logger.error(f"Block {mb.block_id}: This is an IDENTITY TRANSLATION - backend returned source text!")
        # NO CONTEXT BUFFER - Don't maintain context (user doesn't care)
        # NO TRANSLATION MEMORY - Don't save translations (always fresh)

    (out_dir / "translations.json").write_text(
        json.dumps([tb.model_dump() for tb in translated_blocks], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # 3.5) Post-translation scoring
    console.print("[cyan]Computing post-translation quality scores...[/cyan]")
    post_scores = []
    masked_by_id = {mb.block_id: mb for mb in masked_blocks}
    for tb in translated_blocks:
        mb = masked_by_id.get(tb.block_id)
        if not mb:
            continue
        post_score = compute_post_translation_score(
            block_id=tb.block_id,
            source_text=tb.source_text,
            translated_text=tb.translated_text,
            registry=mb.registry,
            errors=tb.errors,
        )
        post_scores.append(post_score)

    (out_dir / "post_scores.json").write_text(
        json.dumps([s.__dict__ for s in post_scores], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"[green]✓ Post-scored {len(post_scores)} blocks[/green]")

    # 3.6) Compute health scores
    health_scores = []
    masked_by_id = {mb.block_id: mb for mb in masked_blocks}
    blocks_by_id = {}
    for page in doc.pages:
        for block in page.blocks:
            blocks_by_id[block.id] = block

    for tb in translated_blocks:
        block = blocks_by_id.get(tb.block_id)
        mb = masked_by_id.get(tb.block_id)
        if block and mb:
            health = compute_block_health(
                block=block,
                translated_block=tb,
                registry=mb.registry,
                check_overflow=True,
                original_bbox=block,
            )
            health_scores.append(health)

    # Compute page-level metrics
    page_metrics = {}
    for page_idx in range(len(doc.pages)):
        try:
            layout_metrics = compute_block_overlap_metrics(doc, page_index=page_idx)
            page_metrics[f"page_{page_idx + 1}"] = {
                "overlap_pairs": layout_metrics.overlap_pairs,
                "mean_iou": layout_metrics.mean_iou,
            }
        except Exception:
            pass

    (out_dir / "health_scores.json").write_text(
        json.dumps([h.__dict__ for h in health_scores], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # DEBUG: Verify all blocks have translations
    logger.info(f"Rendering with {len(translations)} translations")
    console.print(f"[cyan]📊 Rendering: {len(translations)} translations stored[/cyan]")
    
    all_block_ids = set()
    for page in doc.pages:
        for block in page.blocks:
            if block.type == "text":
                all_block_ids.add(block.id)
    
    missing_blocks = all_block_ids - set(translations.keys())
    if missing_blocks:
        logger.error(f"❌ {len(missing_blocks)} blocks have NO translation: {list(missing_blocks)[:10]}...")
        console.print(f"[red]❌ ERROR: {len(missing_blocks)} blocks missing translations![/red]")
        # Log which blocks are missing
        for bid in list(missing_blocks)[:5]:
            # Find the block to see what text it has
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == bid:
                        source_text = _block_text(block)
                        logger.error(f"  Missing block {bid}: '{source_text[:60]}...'")
                        console.print(f"[red]  Missing: {bid} - '{source_text[:40]}...'[/red]")
                        break
    
    # DEBUG: Log ALL translations with block IDs for first page (VERBOSE)
    console.print(f"[cyan]📋 Translations dictionary contents (first page blocks):[/cyan]")
    for page_idx, page in enumerate(doc.pages[:1]):  # First page only
        console.print(f"  Page {page_idx+1} blocks:")
        for block in page.blocks:
            if block.type == "text":
                source_text = _block_text(block)
                stored_trans = translations.get(block.id, "❌ MISSING")
                if stored_trans == "❌ MISSING":
                    console.print(f"    ❌ Block {block.id}: MISSING!")
                    console.print(f"       Source: '{source_text[:60]}...'")
                else:
                    console.print(f"    ✅ Block {block.id}:")
                    console.print(f"       Source: '{source_text[:60]}...'")
                    console.print(f"       Translation: '{stored_trans[:60] if len(stored_trans) > 60 else stored_trans}...'")
    
    # Verify we have translations for all masked blocks
    masked_block_ids = {mb.block_id for mb in masked_blocks}
    missing_masked = masked_block_ids - set(translations.keys())
    if missing_masked:
        logger.error(f"❌ {len(missing_masked)} MASKED blocks have NO translation stored!")
        console.print(f"[red]❌ CRITICAL: {len(missing_masked)} masked blocks missing from translations dict![/red]")

    # 4) Render - select renderer based on mode
    if cfg.render_mode == "perfect":
        # Perfect renderer (100% font size preservation, exact positioning, bullet preservation)
        render_translated_pdf_perfect(
            source_pdf=input_pdf,
            doc=doc,
            translations=translations,
            output_pdf=output_pdf,
            cfg=cfg.render,
            assets_dir=cfg.assets_dir,
            translate_tables=cfg.translate_tables,
        )
    elif cfg.render_mode == "enhanced":
        # Enhanced renderer (preserves titles, headers, bold, bullets)
        render_translated_pdf_enhanced(
            source_pdf=input_pdf,
            doc=doc,
            translations=translations,
            output_pdf=output_pdf,
            cfg=cfg.render,
            assets_dir=cfg.assets_dir,
            translate_tables=cfg.translate_tables,
        )
    elif cfg.render_mode in ("auto", "math-aware"):
        # Use math-aware renderer (preserve equation spans)
        render_translated_pdf_math_aware(
            source_pdf=input_pdf,
            doc=doc,
            translations=translations,
            output_pdf=output_pdf,
            cfg=MathAwareRenderConfig(**cfg.render.__dict__, translate_tables=cfg.translate_tables),
            assets_dir=cfg.assets_dir,
        )
    elif cfg.render_mode == "math-safe":
        # Legacy math-safe renderer (redacts all text)
        render_translated_pdf(
            source_pdf=input_pdf,
            doc=doc,
            translations=translations,
            output_pdf=output_pdf,
            cfg=cfg.render,
            assets_dir=cfg.assets_dir,
            translate_tables=cfg.translate_tables,
        )
    else:
        raise ValueError(
            f"Invalid render_mode: {cfg.render_mode}. Must be 'perfect', 'enhanced', 'auto', 'math-aware', or 'math-safe'."
        )

    # Aggregate all metrics
    page_health = compute_page_health(health_scores)
    failed_block_ids = [h.block_id for h in health_scores if h.needs_repair()]
    scoring_summary = aggregate_scores(pre_scores, post_scores)

    report = {
        "input_pdf": input_pdf,
        "output_pdf": output_pdf,
        "backend": getattr(backend, "name", "unknown"),
        "model": getattr(backend, "model", None),
        "num_blocks": len(masked_blocks),
        "num_ok": sum(1 for tb in translated_blocks if tb.ok),
        "num_failed": sum(1 for tb in translated_blocks if not tb.ok),
        "elapsed_s": time.time() - t0,
        "artifacts_dir": str(out_dir),
        # Phase 5: Health metrics
        "health": {
            "mean_score": page_health["mean_score"],
            "ok_blocks": page_health["ok_blocks"],
            "warning_blocks": page_health["warning_blocks"],
            "failed_blocks": page_health["failed_blocks"],
            "health_ratio": page_health["health_ratio"],
            "failed_block_ids": failed_block_ids,
        },
        "layout_metrics": page_metrics,
        # Pre/Post scoring
        "scoring": scoring_summary,
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print scoring summary
    console.print("\n[bold cyan]Translation Quality Summary:[/bold cyan]")
    console.print(f"  Document Quality: {scoring_summary['document_quality']:.2%}")
    console.print(f"  Confidence: {scoring_summary['document_confidence']:.2%}")
    console.print(f"  Acceptance Rate: {scoring_summary['acceptance_rate']:.2%}")
    console.print(f"  Blocks needing review: {scoring_summary['blocks_need_review']}")
    console.print(f"  Blocks needing retry: {scoring_summary['blocks_need_retry']}")

    return report


def repair_failed_blocks(
    *,
    input_pdf: str,
    output_pdf: str,
    artifacts_dir: str,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    glossary: Optional[dict[str, str]] = None,
    block_ids: Optional[list[str]] = None,
) -> dict:
    """Selectively repair failed blocks from a previous translation run.

    This enables fixing a document by retranslating only problematic blocks,
    rather than re-running the entire pipeline.
    """
    out_dir = Path(artifacts_dir)

    # Load previous artifacts
    doc = Document.model_validate_json((out_dir / "parsed.json").read_text(encoding="utf-8"))
    masked_data = json.loads((out_dir / "masked.json").read_text(encoding="utf-8"))
    translations_data = json.loads((out_dir / "translations.json").read_text(encoding="utf-8"))
    health_data = json.loads((out_dir / "health_scores.json").read_text(encoding="utf-8"))

    # Build lookup structures
    masked_by_id = {mb["block_id"]: MaskedBlock(**mb) for mb in masked_data}
    translations_by_id = {tb["block_id"]: TranslatedBlock(**tb) for tb in translations_data}

    # Determine which blocks to repair
    if block_ids is None:
        # Repair all failed blocks
        block_ids = [h["block_id"] for h in health_data if h["status"] == "failed"]

    if not block_ids:
        console.print("[green]No blocks to repair[/green]")
        return {"repaired": 0, "still_failed": 0}

    console.print(f"[yellow]Repairing {len(block_ids)} blocks[/yellow]")

    masker = MaskingEngine()
    system_prompt = build_system_prompt(
        source=cfg.source_lang, target=cfg.target_lang, glossary=glossary
    )

    # Stronger prompt for repair
    repair_prompt = (
        system_prompt
        + "\n\nCRITICAL REPAIR MODE:\n- You MUST preserve ALL placeholders exactly.\n- Preserve all numbers and formatting.\n- This is a retry - be extra careful."
    )

    repaired_count = 0
    still_failed_count = 0

    for block_id in block_ids:
        mb = masked_by_id.get(block_id)
        if not mb:
            continue

        # Retranslate with stronger constraints
        req = TranslateRequest(
            text=mb.masked_text,
            source_lang=cfg.source_lang,
            target_lang=cfg.target_lang,
            system_prompt=repair_prompt,
            temperature=max(0.0, cfg.temperature - 0.3),  # Lower temperature
            n_candidates=cfg.n_candidates,
        )

        try:
            res = backend.translate(req)
            candidates = res.candidates if res.candidates else [""]

            # Rerank if multiple candidates
            if cfg.enable_reranking and len(candidates) > 1:
                # Get source text
                source_text = ""
                for page in doc.pages:
                    for block in page.blocks:
                        if block.id == block_id:
                            source_text = _block_text(block)
                            break

                ranked = rerank_candidates(
                    candidates=candidates,
                    source_text=source_text,
                    registry=mb.registry,
                    glossary=glossary,
                )
                if ranked:
                    candidates = [c for c, _ in ranked]

            candidate = candidates[0] if candidates else ""
            restored, errors = masker.restore(candidate, mb.registry, tolerant=True)

            ok = (
                candidate.strip() != ""
                and len(errors) == 0
                and masker.placeholders_present(candidate, mb.registry)
            )

            if ok:
                # Update translation
                translations_by_id[block_id] = TranslatedBlock(
                    block_id=block_id,
                    source_text=mb.masked_text,
                    translated_text=restored,
                    ok=True,
                    errors=[],
                    meta={"repaired": True, **res.meta},
                )
                repaired_count += 1
            else:
                still_failed_count += 1
                console.print(f"[red]Block {block_id} still failed after repair[/red]")

        except Exception as e:
            console.print(f"[red]Error repairing block {block_id}: {e}[/red]")
            still_failed_count += 1

    # Save updated translations
    updated_translations = [tb.model_dump() for tb in translations_by_id.values()]
    (out_dir / "translations.json").write_text(
        json.dumps(updated_translations, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Re-render PDF
    translations_dict = {tb.block_id: tb.translated_text for tb in translations_by_id.values()}
    render_translated_pdf(
        source_pdf=input_pdf,
        doc=doc,
        translations=translations_dict,
        output_pdf=output_pdf,
        cfg=cfg.render,
        assets_dir=cfg.assets_dir,
    )

    return {
        "repaired": repaired_count,
        "still_failed": still_failed_count,
        "total_attempted": len(block_ids),
    }
