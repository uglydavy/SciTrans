from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from scitrans.core.models import Document, MaskedBlock, TranslatedBlock
from scitrans.masking.engine import MaskingEngine
from scitrans.metrics.health import compute_block_health, compute_page_health
from scitrans.metrics.layout import (
    compute_block_overlap_metrics,
    compute_rendered_pdf_overlap_metrics,
)
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
from scitrans.utils.identity_translation_detector import (
    check_identity_translation,
    IdentityCheckResult,
)

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


def _translate_single_block(
    mb: MaskedBlock,
    idx: int,
    total: int,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    doc: Document,
    masker: MaskingEngine,
    glossary: Optional[dict[str, str]],
    pre_scores_by_id: dict[str, Any],
    cancel_event: threading.Event,
) -> tuple[TranslatedBlock, str]:
    """Translate a single block. Returns (TranslatedBlock, translated_text)."""
    if cancel_event.is_set():
        raise RuntimeError("Translation cancelled by user")
    
    # Get source text
    source_text = ""
    for page in doc.pages:
        for block in page.blocks:
            if block.id == mb.block_id:
                source_text = _block_text(block)
                break
    
    logger.info(f"[{idx+1}/{total}] Translating block {mb.block_id}")
    pre_score = pre_scores_by_id.get(mb.block_id)
    
    # Adapt parameters based on complexity
    if pre_score and pre_score.is_complex():
        block_n_candidates = pre_score.recommended_candidates
        block_temperature = pre_score.recommended_temperature
    else:
        block_n_candidates = cfg.n_candidates
        block_temperature = cfg.temperature
    
    # Get block metadata
    is_header_block = False
    is_bullet_block = False
    for page in doc.pages:
        for block in page.blocks:
            if block.id == mb.block_id:
                is_header_block = block.meta.get("is_header", False)
                source_text_check = _block_text(block)
                is_bullet_block = any(source_text_check.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"])
                break
    
    # Build enhanced prompt
    enhanced_prompt = build_system_prompt(
        source=cfg.source_lang,
        target=cfg.target_lang,
        glossary=glossary,
        is_header=is_header_block,
        is_bullet=is_bullet_block,
    )
    
    # Create translation request
    req = TranslateRequest(
        text=mb.masked_text,
        source_lang=cfg.source_lang,
        target_lang=cfg.target_lang,
        system_prompt=enhanced_prompt,
        temperature=block_temperature,
        n_candidates=block_n_candidates,
        context="",
    )
    
    # Translate
    candidates: list[str] = []
    res_meta: dict = {}
    try:
        if cancel_event.is_set():
            raise RuntimeError("Translation cancelled by user")
        res = backend.translate(req)
        candidates = res.candidates if res.candidates else [""]
        res_meta = {
            "backend": backend.name,
            "model": getattr(backend, "model", cfg.model),
            "cached": False,
            **res.meta,
        }
    except Exception as e:
        logger.error(f"Block {mb.block_id}: Backend translation failed: {e}", exc_info=True)
        candidates = [""]
        res_meta = {"backend": backend.name, "model": getattr(backend, "model", cfg.model), "cached": False, "error": str(e)}
    
    # Rerank if enabled
    if cfg.enable_reranking and len(candidates) > 1:
        is_header_for_rerank = False
        for page in doc.pages:
            for block in page.blocks:
                if block.id == mb.block_id:
                    is_header_for_rerank = block.meta.get("is_header", False)
                    break
        ranked = rerank_candidates(
            candidates=candidates,
            source_text=source_text,
            registry=mb.registry,
            glossary=glossary,
            is_header=is_header_for_rerank,
        )
        if ranked:
            candidates = [c for c, _ in ranked]
            res_meta["rerank_scores"] = {"best_score": ranked[0][1].total, "best_valid": ranked[0][1].is_valid()}
    
    # Restore placeholders
    candidate = candidates[0] if candidates else ""
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:195","message":"Before restore","data":{"block_id":mb.block_id,"candidate_len":len(candidate),"candidate_preview":candidate[:100],"num_candidates":len(candidates),"registry_size":len(mb.registry) if mb.registry else 0}})+'\n')
    # #endregion
    restored, restore_errors = masker.restore(candidate, mb.registry, tolerant=True)
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:197","message":"After restore","data":{"block_id":mb.block_id,"restored_len":len(restored),"restored_preview":restored[:100],"restore_errors":restore_errors,"num_restore_errors":len(restore_errors)}})+'\n')
    # #endregion
    
    # Check identity translation
    identity_translation = False
    wrong_translation = False
    if restored.strip():
        identity_result = check_identity_translation(
            source_text,
            restored,
            is_header=is_header_block,
            is_bullet=is_bullet_block,
        )
        identity_translation = identity_result.is_identity and identity_result.should_retry
        
        # Check for generic responses
        generic_phrases = ["je suis ravi", "pouvez-vous", "i'm happy to help", "can you"]
        if any(phrase in restored.lower() for phrase in generic_phrases):
            wrong_translation = True
    
    # Validate
    # Handle None or empty registry
    registry = mb.registry if mb.registry is not None else {}
    
    # Check if candidate is empty (backend failed)
    candidate_empty = candidate.strip() == ""
    if candidate_empty:
        logger.error(f"Block {mb.block_id}: Backend returned EMPTY candidate! This means all backends failed.")
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"B","location":"pipeline.py:232","message":"Empty candidate from backend","data":{"block_id":mb.block_id,"num_candidates":len(candidates),"backend":res_meta.get("backend","unknown")}})+'\n')
        # #endregion
    
    placeholders_ok = (
        not candidate_empty
        and (len(registry) == 0 or masker.placeholders_present(candidate, registry))
    )
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        validation_details = {
            "block_id": mb.block_id,
            "placeholders_ok": placeholders_ok,
            "candidate_empty": candidate_empty,
            "registry_size": len(registry),
            "registry_is_none": mb.registry is None,
            "placeholders_present": masker.placeholders_present(candidate, registry) if candidate.strip() and registry else (len(registry) == 0),
            "restore_errors_count": len(restore_errors),
            "restore_errors": restore_errors,
            "identity_translation": identity_translation,
            "wrong_translation": wrong_translation,
            "restored_empty": restored.strip() == "",
            "restored_len": len(restored),
            "backend": res_meta.get("backend", "unknown"),
            "backend_meta": res_meta,
        }
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:250","message":"Validation details","data":validation_details})+'\n')
    # #endregion
    ok = placeholders_ok and len(restore_errors) == 0 and not identity_translation and not wrong_translation and restored.strip() != ""
    
    # Create TranslatedBlock
    tb = TranslatedBlock(
        block_id=mb.block_id,
        source_text=mb.masked_text,
        translated_text=restored,
        ok=ok,
        errors=restore_errors if restore_errors else ([] if ok else ["validation_failed"]),
        meta=res_meta,
    )
    
    return tb, restored


def run_pipeline(
    *,
    input_pdf: str,
    output_pdf: str,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    glossary: Optional[dict[str, str]] = None,
    progress: Optional[Any] = None,
    cancel_event: Optional[threading.Event] = None,
) -> dict:
    t0 = time.time()
    logger.info(f"Starting translation pipeline: {input_pdf} -> {output_pdf}")
    logger.debug(f"Backend: {backend.name}, Config: {cfg}")
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:243","message":"Pipeline started","data":{"input_pdf":input_pdf,"output_pdf":output_pdf,"backend":backend.name,"parallel":cfg.parallel_translation,"max_workers":cfg.max_workers,"n_candidates":cfg.n_candidates}})+'\n')
    # #endregion
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

    # 2) Mask - Extract ALL text blocks (headers, titles, paragraphs, numbering, etc.)
    masker = MaskingEngine()
    masked_blocks: list[MaskedBlock] = []
    skipped_blocks = []
    total_text_blocks = 0
    header_count = 0
    title_count = 0
    translations: dict[str, str] = {}  # Initialize early for language preservation
    
    for page in doc.pages:
        for block in page.blocks:
            if block.type != "text":
                continue
            total_text_blocks += 1
            src = _block_text(block)
            
            # Translate table of contents, figures, captions by default
            # These should be translated unless user explicitly says otherwise
            is_toc = ("table of contents" in src.lower() or "contents" in src.lower()) and len(src) < 100
            is_figure_caption = any(keyword in src.lower() for keyword in ["figure", "fig.", "table", "tab."]) and len(src) < 200
            if is_toc or is_figure_caption:
                logger.debug(f"Translating TOC/figure block {block.id}: {src[:50]}...")
            
            # PHASE 4: Translate tables, TOC, figures by default (user can disable with --preserve-tables)
            # Only skip tables if user explicitly requested to preserve them
            # But always translate table of contents, figures, and captions
            is_table_region = block.meta.get("region") == "table"
            is_toc_or_figure = is_toc or is_figure_caption
            if is_table_region and not cfg.translate_tables and not is_toc_or_figure:
                skipped_blocks.append((block.id, "table"))
                logger.debug(f"Skipping table block {block.id} (preserve-tables enabled, not TOC/figure)")
                # Store source text so table is preserved in rendered PDF
                translations[block.id] = src
                continue
            # Skip empty blocks BUT store source text so they're rendered
            if not src.strip():
                skipped_blocks.append((block.id, "empty"))
                logger.debug(f"Skipping empty block {block.id} (storing source text for rendering)")
                # Store source text so block is rendered (even if empty)
                translations[block.id] = src
                continue
            
            # PHASE 4.5: Detect and preserve blocks in languages other than source/target
            # If a block is in a language other than source or target, preserve it untranslated
            from scitrans.utils.language_detection import detect_language
            detected_lang, lang_confidence = detect_language(src)
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"N","location":"pipeline.py:150","message":"Language detection result","data":{"block_id":block.id,"detected_lang":detected_lang,"lang_confidence":lang_confidence,"source_lang":cfg.source_lang,"target_lang":cfg.target_lang,"source_preview":src[:50]}})+'\n')
            # #endregion
            
            if detected_lang not in (cfg.source_lang, cfg.target_lang) and lang_confidence > 0.5:
                # Block is in a different language - preserve it
                skipped_blocks.append((block.id, f"preserve_lang_{detected_lang}"))
                logger.info(
                    f"Preserving block {block.id} in language {detected_lang} "
                    f"(confidence: {lang_confidence:.2f}) - not translating"
                )
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"N","location":"pipeline.py:160","message":"Preserving block due to language","data":{"block_id":block.id,"detected_lang":detected_lang,"lang_confidence":lang_confidence,"source_preview":src[:50]}})+'\n')
                # #endregion
                # Store original text as translation to preserve it
                translations[block.id] = src
                continue
            
            # Log headers/titles for visibility
            if block.meta.get("is_header"):
                block_type = block.meta.get("block_type", "header")
                if block_type == "title":
                    title_count += 1
                    logger.debug(f"Detected TITLE block {block.id}: '{src[:50]}...'")
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:375","message":"TITLE detected during parsing","data":{"block_id":block.id,"block_type":block_type,"source_preview":src[:50]}})+'\n')
                    # #endregion
                else:
                    header_count += 1
                    logger.debug(f"Detected HEADER block {block.id}: '{src[:50]}...'")
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:379","message":"HEADER detected during parsing","data":{"block_id":block.id,"block_type":block_type,"source_preview":src[:50]}})+'\n')
                    # #endregion
            # Pass block to masker for advanced span-level math detection
            masked, registry, counts = masker.mask(src, block=block)
            masked_blocks.append(
                MaskedBlock(
                    block_id=block.id, masked_text=masked, registry=registry, mask_counts=counts
                )
            )
            # #region agent log
            if block.meta.get("is_header"):
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"A","location":"pipeline.py:386","message":"Header/title added to masked_blocks","data":{"block_id":block.id,"block_type":block.meta.get("block_type","header"),"masked_len":len(masked)}})+'\n')
            # #endregion
    
    logger.info(f"Masked {len(masked_blocks)} blocks for translation (headers, titles, paragraphs, numbering included)")
    console.print(f"[cyan]✓ Extracted {total_text_blocks} text blocks, masking {len(masked_blocks)} for translation[/cyan]")
    if title_count > 0 or header_count > 0:
        console.print(f"[cyan]  → Detected {title_count} titles and {header_count} headers[/cyan]")
    if skipped_blocks:
        skipped_tables = len([s for s in skipped_blocks if s[1] == "table"])
        skipped_empty = len([s for s in skipped_blocks if s[1] == "empty"])
        logger.info(f"Skipped {len(skipped_blocks)} blocks: {skipped_tables} tables, {skipped_empty} empty")
        console.print(f"[yellow]  Skipped: {skipped_tables} tables, {skipped_empty} empty blocks[/yellow]")
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

    # Initialize cancel event if not provided
    if cancel_event is None:
        cancel_event = threading.Event()

    logger.info(f"Starting translation of {len(masked_blocks)} blocks...")
    if cfg.parallel_translation:
        console.print(f"[cyan]🔄 Translating {len(masked_blocks)} blocks in parallel ({cfg.max_workers} workers)...[/cyan]")
    else:
        console.print(f"[cyan]🔄 Translating {len(masked_blocks)} blocks...[/cyan]")
    # Check if progress is callable WITHOUT checking truthiness first (Gradio progress objects have __len__ that can fail)
    # Use try/except to safely check and call progress
    def safe_progress_update(progress_val: float, desc: str):
        """Safely update progress, handling Gradio progress objects that may fail on __len__."""
        if progress is None:
            return
        try:
            # Check if it's callable without triggering __len__
            if hasattr(progress, '__call__'):
                progress(progress_val, desc=desc)
        except (IndexError, AttributeError, TypeError):
            # Ignore progress errors - it's not critical
            pass
    
    safe_progress_update(0.3, desc=f"Translating {len(masked_blocks)} blocks...")
    
    # Check for cancellation before starting
    if cancel_event.is_set():
        logger.warning("Translation cancelled before starting")
        raise RuntimeError("Translation cancelled by user")
    
    # Use parallel translation if enabled
    # NOTE: cascade_free already parallelizes internally (Ollama + Google in parallel)
    # So we disable pipeline-level parallelization for cascade_free to avoid nested threading issues
    should_use_parallel = (
        cfg.parallel_translation 
        and len(masked_blocks) > 1 
        and backend.name != "cascade_free"
    )
    if backend.name == "cascade_free" and cfg.parallel_translation:
        logger.info(
            "cascade_free backend detected: Disabling pipeline-level parallelization "
            "(cascade_free already runs Ollama + Google in parallel internally)"
        )
    if should_use_parallel:
        logger.info(f"Using parallel translation with {cfg.max_workers} workers")
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"B","location":"pipeline.py:438","message":"Parallel translation path selected","data":{"num_blocks":len(masked_blocks),"max_workers":cfg.max_workers}})+'\n')
        # #endregion
        translated_blocks_dict: dict[str, TranslatedBlock] = {}
        translations_dict: dict[str, str] = {}
        completed = 0
        
        def translate_block_parallel(mb: MaskedBlock, idx: int) -> tuple[str, TranslatedBlock, str]:
            """Translate a block in parallel - simplified version without retry."""
            if cancel_event.is_set():
                raise RuntimeError("Translation cancelled")
            try:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"E","location":"pipeline.py:444","message":"Starting parallel block translation","data":{"block_id":mb.block_id,"idx":idx,"total":len(masked_blocks)}})+'\n')
                # #endregion
                tb, restored = _translate_single_block(
                    mb, idx, len(masked_blocks), backend, cfg, doc, masker, glossary, pre_scores_by_id, cancel_event
                )
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"E","location":"pipeline.py:451","message":"Parallel block translation completed","data":{"block_id":mb.block_id,"ok":tb.ok,"restored_len":len(restored),"errors":tb.errors}})+'\n')
                # #endregion
                return mb.block_id, tb, restored
            except RuntimeError:
                raise  # Re-raise cancellation
            except Exception as e:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"E","location":"pipeline.py:457","message":"Parallel block translation failed","data":{"block_id":mb.block_id,"error":str(e),"error_type":type(e).__name__}})+'\n')
                # #endregion
                logger.error(f"Block {mb.block_id}: Parallel translation failed: {e}", exc_info=True)
                # Return failed block
                tb = TranslatedBlock(
                    block_id=mb.block_id,
                    source_text=mb.masked_text,
                    translated_text="",
                    ok=False,
                    errors=[f"parallel_error: {e}"],
                    meta={},
                )
                return mb.block_id, tb, ""
        
        # Execute in parallel
        with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
            future_to_block = {
                executor.submit(translate_block_parallel, mb, idx): mb
                for idx, mb in enumerate(masked_blocks)
            }
            
            for future in as_completed(future_to_block):
                if cancel_event.is_set():
                    logger.warning("Translation cancelled - stopping parallel execution")
                    # Cancel remaining futures
                    for f in future_to_block:
                        f.cancel()
                    raise RuntimeError("Translation cancelled by user")
                
                mb = future_to_block[future]
                try:
                    block_id, tb, restored = future.result()
                    translated_blocks_dict[block_id] = tb
                    translations_dict[block_id] = restored
                    completed += 1
                    block_progress = 0.3 + (completed / len(masked_blocks)) * 0.5
                    safe_progress_update(block_progress, desc=f"Translated {completed}/{len(masked_blocks)} blocks...")
                    if tb.ok:
                        logger.info(f"Block {block_id}: ✅ OK")
                    else:
                        logger.warning(f"Block {block_id}: ❌ FAILED - {tb.errors}")
                except Exception as e:
                    logger.error(f"Block {mb.block_id}: Future exception: {e}", exc_info=True)
                    tb = TranslatedBlock(
                        block_id=mb.block_id,
                        source_text=mb.masked_text,
                        translated_text="",
                        ok=False,
                        errors=[f"future_error: {e}"],
                        meta={},
                    )
                    translated_blocks_dict[mb.block_id] = tb
                    translations_dict[mb.block_id] = ""
                    completed += 1
        
        # Convert dicts to lists
        translated_blocks = list(translated_blocks_dict.values())
        translations = translations_dict
        logger.info(f"Parallel translation complete: {completed}/{len(masked_blocks)} blocks")
    else:
        # Sequential translation (original logic with retry)
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"pipeline.py:515","message":"Sequential translation path selected","data":{"num_blocks":len(masked_blocks),"parallel_enabled":cfg.parallel_translation}})+'\n')
        # #endregion
        for idx, mb in enumerate(masked_blocks):  # Get pre-score for adaptive strategy
            # Check for cancellation
            if cancel_event.is_set():
                logger.warning("Translation cancelled during sequential execution")
                raise RuntimeError("Translation cancelled by user")
            
            # Always log progress for every block
            block_progress = 0.3 + (idx / len(masked_blocks)) * 0.5  # 30% to 80% of total progress
            safe_progress_update(block_progress, desc=f"Translating block {idx+1}/{len(masked_blocks)}...")
            
            # Get source text for logging
            source_text = ""
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text = _block_text(block)
                        break
            
            # Log every block with source text
            logger.info(f"[{idx+1}/{len(masked_blocks)}] Translating block {mb.block_id}")
            logger.info(f"  Source text ({len(source_text)} chars): {source_text[:100]}...")
            console.print(f"[cyan][{idx+1}/{len(masked_blocks)}] Block {mb.block_id}: '{source_text[:60]}...'[/cyan]")
            pre_score = pre_scores_by_id.get(mb.block_id)

            # Get block metadata early for adaptive candidate selection
            is_header_block = False
            is_bullet_block = False
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        is_header_block = block.meta.get("is_header", False)
                        source_text_check = _block_text(block)
                        is_bullet_block = any(source_text_check.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"])
                        break

            # Adapt parameters based on complexity - IMPROVED: More candidates for better accuracy
            if pre_score and pre_score.is_complex():
                # Complex block: use recommended settings, but increase candidates for accuracy
                block_n_candidates = max(pre_score.recommended_candidates, 3)  # At least 3 candidates for complex blocks
                block_temperature = pre_score.recommended_temperature
                console.print(
                f"[yellow]Complex block {mb.block_id}: using {block_n_candidates} candidates, temp={block_temperature}[/yellow]"
            )
            elif is_header_block:
                # Headers/titles: use more candidates for better accuracy
                block_n_candidates = max(cfg.n_candidates, 3)  # At least 3 candidates for headers
                block_temperature = cfg.temperature
                logger.info(f"Block {mb.block_id}: Header block - using {block_n_candidates} candidates for accuracy")
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"B","location":"pipeline.py:651","message":"Header/title translation starting","data":{"block_id":mb.block_id,"n_candidates":block_n_candidates,"source_preview":source_text[:50]}})+'\n')
                # #endregion
            else:
                # Normal block: use config settings, but ensure at least 2 candidates if reranking is enabled
                block_n_candidates = max(cfg.n_candidates, 2 if cfg.enable_reranking else 1)
            block_temperature = cfg.temperature

            # NO CACHE, NO MEMORY - Always translate fresh
            cache_key = None
            cached_result = None
            memory_match = None

            candidates: list[str] = []
            res_meta: dict = {}

            # Build enhanced prompt for headers/bullets
            # Build enhanced prompt for headers/bullets
            enhanced_prompt = build_system_prompt(
                source=cfg.source_lang,
                target=cfg.target_lang,
                glossary=glossary,
                is_header=is_header_block,
                is_bullet=is_bullet_block,
            )
            # Store system_prompt for retry logic (use enhanced_prompt as base)
            system_prompt = enhanced_prompt
            
            # Build context from previous blocks if context_window > 0
            context_text = ""
            if cfg.context_window > 0 and idx > 0:
                # Get previous N translated blocks for context
                context_blocks = []
                start_idx = max(0, idx - cfg.context_window)
                for prev_idx in range(start_idx, idx):
                    if prev_idx < len(translated_blocks):
                        prev_block = translated_blocks[prev_idx]
                        if prev_block.translated_text and prev_block.translated_text.strip():
                            # CRITICAL: Clean instruction spillover from context to prevent pollution
                            from scitrans.utils.translation_cleaner import clean_instruction_spillover
                            cleaned_context_block = clean_instruction_spillover(prev_block.translated_text.strip())
                            if cleaned_context_block and cleaned_context_block.strip():
                                context_blocks.append(cleaned_context_block)
                
                if context_blocks:
                    context_text = "\n\n".join(context_blocks)
                    logger.debug(f"Block {mb.block_id}: Using context from {len(context_blocks)} previous blocks")
                    console.print(f"[dim]  📚 Using context from {len(context_blocks)} previous blocks[/dim]")
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"A","location":"pipeline.py:728","message":"Context window built","data":{"block_id":mb.block_id,"context_window":cfg.context_window,"context_blocks_count":len(context_blocks),"context_length":len(context_text),"context_preview":context_text[:100] if context_text else ""}})+'\n')
                    # #endregion
                else:
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"A","location":"pipeline.py:732","message":"Context window empty","data":{"block_id":mb.block_id,"context_window":cfg.context_window,"idx":idx,"translated_blocks_count":len(translated_blocks)}})+'\n')
                    # #endregion
            else:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"A","location":"pipeline.py:736","message":"Context window disabled or first block","data":{"block_id":mb.block_id,"context_window":cfg.context_window,"idx":idx}})+'\n')
                # #endregion
            
            # CRITICAL: Special handling for blocks that are ENTIRELY placeholders
            # If the masked text is only a placeholder (e.g., "<<PERSON_NAME_0001>>"),
            # we should NOT translate it - just return it unchanged
            masked_text_stripped = mb.masked_text.strip()
            # Check if it's a placeholder format (<<...>> or ⟦...⟧)
            is_placeholder_format = (
                (masked_text_stripped.startswith("<<") and masked_text_stripped.endswith(">>")) or
                (masked_text_stripped.startswith("⟦") and masked_text_stripped.endswith("⟧"))
            )
            # Check if it contains placeholder keywords
            has_placeholder_keyword = any(
                keyword in masked_text_stripped for keyword in [
                    "PERSON_NAME", "PLACE_NAME", "MATH_", "TABLE_", 
                    "FIGURE_", "TOC_", "URL_", "EMAIL_", "CODEBLOCK", "INLINECODE"
                ]
            )
            # Check if it's only one "word" (the placeholder itself)
            is_single_token = len(masked_text_stripped.split()) == 1
            
            is_only_placeholder = is_placeholder_format and has_placeholder_keyword and is_single_token
            
            if is_only_placeholder:
                logger.info(f"Block {mb.block_id}: Block is ONLY a placeholder - preserving unchanged: {masked_text_stripped}")
                console.print(f"[cyan]  ℹ Block is only a placeholder - preserving unchanged[/cyan]")
                candidates = [masked_text_stripped]  # Return placeholder unchanged
                res_meta = {
                    "backend": backend.name,
                    "model": getattr(backend, "model", cfg.model),
                    "cached": False,
                    "note": "Placeholder-only block - not translated",
                }
            else:
                # Translate with context if available
                req = TranslateRequest(
                    text=mb.masked_text,
                    source_lang=cfg.source_lang,
                    target_lang=cfg.target_lang,
                    system_prompt=enhanced_prompt,  # Use enhanced prompt
                    temperature=block_temperature,
                    n_candidates=block_n_candidates,
                    context=context_text,  # Include context from previous blocks for better quality
                )

                # DEBUG: Log what we're sending to backend
                masked_preview = mb.masked_text[:80] + "..." if len(mb.masked_text) > 80 else mb.masked_text
                logger.info(f"Block {mb.block_id}: Sending to backend (masked, {len(mb.masked_text)} chars): {masked_preview}")
                logger.debug(f"Block {mb.block_id}: Full masked text: {mb.masked_text}")

                try:
                    res = backend.translate(req)
                    candidates = res.candidates if res.candidates else [""]
                
                    # CRITICAL: Clean instruction spillover from backend responses
                    from scitrans.utils.translation_cleaner import clean_instruction_spillover
                    cleaned_candidates = []
                    for cand in candidates:
                        if cand and cand.strip():
                            cleaned = clean_instruction_spillover(cand)
                            if cleaned and cleaned.strip():
                                cleaned_candidates.append(cleaned)
                            else:
                                # If cleaning removed everything, keep original (might be a false positive)
                                cleaned_candidates.append(cand)
                        else:
                            cleaned_candidates.append(cand)
                    
                    candidates = cleaned_candidates
                    
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
                        logger.debug(f"Block {mb.block_id}: Full backend response: {candidates[0]}")
                        console.print(f"[cyan]  ✓ Backend returned {len(candidates[0])} chars[/cyan]")
                    else:
                        logger.warning(f"Block {mb.block_id}: Backend returned EMPTY translation!")
                        console.print(f"[red]  ✗ Backend returned EMPTY![/red]")

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
                        "error_type": type(e).__name__,
                    }
                    console.print(f"[red]❌ Block {mb.block_id}: Translation error: {e}[/red]")
                    # Continue processing - don't let one block failure stop the entire pipeline
            # NO CACHING - Don't store results

            # Get source text for comparison (unmasked)
            source_text_for_rerank = mb.masked_text
            # Find original source text from document
            is_header_for_rerank = False
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text_for_rerank = _block_text(block)
                        is_header_for_rerank = block.meta.get("is_header", False)
                        break

            # CRITICAL FIX: Filter out identity translations BEFORE reranking
            # Headers/titles should NEVER accept identity translations
            filtered_candidates = []
            filtered_out_identity = []
            # #region agent log
            if is_header_for_rerank:
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"F","location":"pipeline.py:786","message":"Starting identity filtering for header","data":{"block_id":mb.block_id,"num_candidates":len(candidates),"source_preview":source_text_for_rerank[:50],"is_header":is_header_for_rerank}})+'\n')
            # #endregion
            for cand in candidates:
                if cand.strip():
                    # Normalize for comparison
                    source_norm = " ".join(source_text_for_rerank.strip().split()).lower()
                    cand_norm = " ".join(cand.strip().split()).lower()
                    # #region agent log
                    if is_header_for_rerank:
                        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                            import json
                            f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"F","location":"pipeline.py:793","message":"Comparing candidate","data":{"block_id":mb.block_id,"source_norm":source_norm[:50],"cand_norm":cand_norm[:50],"is_identical":source_norm == cand_norm}})+'\n')
                    # #endregion
                    # For headers/titles: completely reject identity translations
                    if is_header_for_rerank and source_norm == cand_norm:
                        filtered_out_identity.append(cand)
                        logger.warning(f"Block {mb.block_id}: Filtering out identity translation candidate: '{cand[:50]}...'")
                        console.print(f"[yellow]  ⚠ Filtered identity candidate: '{cand[:50]}...'[/yellow]")
                        # #region agent log
                        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                            import json
                            f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"F","location":"pipeline.py:798","message":"Filtered identity candidate","data":{"block_id":mb.block_id,"cand_preview":cand[:50]}})+'\n')
                        # #endregion
                    else:
                        filtered_candidates.append(cand)
            
            # If we filtered out all candidates, keep at least one (but log warning)
            if not filtered_candidates and candidates:
                logger.error(f"Block {mb.block_id}: All candidates were identity translations! Using first candidate anyway.")
                console.print(f"[red]  ⚠ All candidates were identity - using first candidate (will retry)[/red]")
                filtered_candidates = [candidates[0]]
            
            # Rerank candidates if enabled and multiple candidates after filtering
            if cfg.enable_reranking and len(filtered_candidates) > 1:
                console.print(f"[cyan]  🔄 Reranking {len(filtered_candidates)} candidates for block {mb.block_id}...[/cyan]")
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"B","location":"pipeline.py:856","message":"Starting reranking","data":{"block_id":mb.block_id,"num_candidates":len(filtered_candidates),"is_header":is_header_for_rerank}})+'\n')
                # #endregion
                ranked = rerank_candidates(
                    candidates=filtered_candidates,
                    source_text=source_text_for_rerank,
                    registry=mb.registry,
                    glossary=glossary,
                    is_header=is_header_for_rerank,  # Pass header flag for enhanced scoring
                )
            elif len(filtered_candidates) == 1:
                # Single candidate - no need to rerank
                ranked = [(filtered_candidates[0], None)]
            else:
                ranked = []
            if ranked:
                # Log which candidate was selected
                if len(ranked) > 1 and ranked[0][1] is not None:
                    best_score = ranked[0][1].total
                    best_valid = ranked[0][1].is_valid()
                    logger.info(
                        f"Block {mb.block_id}: Reranked {len(ranked)} candidates, "
                        f"best score: {best_score:.2f} (valid: {best_valid})"
                    )
                    console.print(f"[green]  ✓ Reranked: Best candidate score {best_score:.2f} (valid: {best_valid})[/green]")
                    # Show top 3 candidates with scores
                    for i, (cand, score) in enumerate(ranked[:3]):
                        if score is not None:
                            cand_preview = cand[:50] + "..." if len(cand) > 50 else cand
                            console.print(f"[dim]    {i+1}. Score {score.total:.2f}: '{cand_preview}'[/dim]")
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        scores_data = []
                        for i, (cand, score) in enumerate(ranked[:5]):
                            if score is not None:
                                scores_data.append({"rank":i+1,"score":score.total,"valid":score.is_valid(),"candidate_preview":cand[:50]})
                        f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"B","location":"pipeline.py:880","message":"Reranking complete","data":{"block_id":mb.block_id,"num_ranked":len(ranked),"best_score":best_score,"best_valid":best_valid,"top_scores":scores_data}})+'\n')
                    # #endregion
                candidates = [c for c, _ in ranked]
                if ranked[0][1] is not None:
                    res_meta["rerank_scores"] = {
                        "best_score": ranked[0][1].total,
                        "best_valid": ranked[0][1].is_valid(),
                        "num_candidates_ranked": len(ranked),
                    }
            else:
                console.print(f"[yellow]  ⚠ Reranking returned no results, using first candidate[/yellow]")
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"B","location":"pipeline.py:900","message":"Reranking returned no results","data":{"block_id":mb.block_id,"num_filtered_candidates":len(filtered_candidates)}})+'\n')
                # #endregion

            # Validate BEFORE restoration: placeholder preservation is a hard gate
            candidate = candidates[0] if candidates else ""
            placeholders_ok = candidate.strip() != "" and masker.placeholders_present(
                candidate, mb.registry
            )
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                # Check which placeholders are missing
                missing_placeholders = []
                if candidate.strip() and mb.registry:
                    for ph in mb.registry.keys():
                        if ph not in candidate:
                            missing_placeholders.append(ph)
                f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"C","location":"pipeline.py:897","message":"Placeholder validation","data":{"block_id":mb.block_id,"placeholders_ok":placeholders_ok,"candidate_length":len(candidate),"registry_size":len(mb.registry),"missing_placeholders":missing_placeholders[:5]}})+'\n')
            # #endregion
            
            # Log placeholder validation status
            if not placeholders_ok and candidate.strip():
                missing_phs = [ph for ph in mb.registry.keys() if ph not in candidate] if mb.registry else []
                if missing_phs:
                    console.print(f"[red]  ✗ Placeholder validation FAILED: Missing {len(missing_phs)} placeholders: {missing_phs[:3]}[/red]")
                else:
                    console.print(f"[yellow]  ⚠ Placeholder validation: Some placeholders may be missing[/yellow]")
            elif placeholders_ok:
                console.print(f"[green]  ✓ Placeholder validation: All placeholders preserved[/green]")

            # Restore placeholders
            restored, restore_errors = masker.restore(candidate, mb.registry, tolerant=True)
            
            # CRITICAL: Clean instruction spillover from restored text
            if restored and restored.strip():
                from scitrans.utils.translation_cleaner import clean_instruction_spillover
                restored = clean_instruction_spillover(restored)
            
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"C","location":"pipeline.py:909","message":"Placeholder restoration","data":{"block_id":mb.block_id,"restore_errors_count":len(restore_errors),"restore_errors":restore_errors[:3],"restored_length":len(restored) if restored else 0}})+'\n')
            # #endregion
            
            # Log restoration status
            if restore_errors:
                console.print(f"[yellow]  ⚠ Restoration: {len(restore_errors)} errors - {', '.join(restore_errors[:2])}[/yellow]")
            else:
                console.print(f"[green]  ✓ Restoration: Successfully restored placeholders[/green]")

            # Show translation preview in terminal (validation status will be shown later)
            if restored and restored.strip():
                restored_preview = restored[:100] + "..." if len(restored) > 100 else restored
                console.print(f"[green]  → Translation ({len(restored)} chars): '{restored_preview}'[/green]")
            elif restored:
                console.print(f"[yellow]  ⚠ Translation: (empty after restoration)[/yellow]")
            else:
                console.print(f"[red]  ✗ Translation: (failed - no output)[/red]")

            # Initialize identity translation detection variables BEFORE any conditional blocks
            # This ensures they're always defined, even if we skip the placeholder check
            identity_result = IdentityCheckResult(
                is_identity=False,
                confidence=0.0,
                reason="Not checked",
                valid_identical_content=[],
                should_retry=False,
            )
            wrong_translation = False
            identity_translation = False  # Initialize to prevent UnboundLocalError

            # Check if any placeholders remain unreplaced (should not happen)
            remaining_placeholders = re.findall(r'(?:<<|⟦)[A-Z_]+_\d+(?:>>|⟧)', restored)
            if remaining_placeholders:
                # Only warn about placeholders that were actually in the registry (not backend hallucinations)
                actual_missing = []
                for ph_remaining in remaining_placeholders:
                    # Try both formats
                    ph_key = None
                    if ph_remaining.startswith("<<"):
                        ph_key = ph_remaining
                    elif ph_remaining.startswith("⟦"):
                        # Convert ⟦KIND_NUM⟧ to <<KIND_NUM>>
                        inner = ph_remaining[1:-1]
                        ph_key = f"<<{inner}>>"
                    
                    if ph_key and ph_key in mb.registry:
                        # This is a real placeholder that should be restored
                        actual_missing.append(ph_remaining)
                        restored = restored.replace(ph_remaining, mb.registry[ph_key])
                        logger.info(f"Block {mb.block_id}: Manually restored placeholder {ph_remaining} -> {mb.registry[ph_key][:30]}...")
                    else:
                        # Backend hallucinated this placeholder - silently remove it (not a real error)
                        logger.debug(f"Block {mb.block_id}: Removing hallucinated placeholder {ph_remaining} (not in registry)")
                        restored = restored.replace(ph_remaining, "")
                
                # Only warn if we had actual missing placeholders from registry
                if actual_missing:
                    logger.warning(
                        f"Block {mb.block_id}: {len(actual_missing)} placeholders from registry not restored: {actual_missing[:3]}"
                    )

            # DEBUG: Log restored text
            if restored:
                restored_preview = restored[:100] + "..." if len(restored) > 100 else restored
                logger.info(f"Block {mb.block_id}: After restore: {len(restored)} chars: {restored_preview}")
            else:
                logger.warning(f"Block {mb.block_id}: After restore: EMPTY!")

            # Check for identity translation (output == input) - CRITICAL VALIDATION
            # Use improved identity detection with context-aware handling
            # Note: identity_result, wrong_translation, and identity_translation are already initialized above
            
            if restored.strip():
                # Use the source_text we already have from earlier in the loop
                source_text_for_check = source_text
                
                # Check for generic/wrong translations (common LLM responses)
                generic_phrases = [
                    "je suis ravi",
                    "pouvez-vous",
                    "comment puis-je",
                    "i'm happy to help",
                    "can you",
                    "how can i",
                    "aucun texte fourni",
                    "no text provided",
                ]
                restored_lower = restored.lower()
                if any(phrase in restored_lower for phrase in generic_phrases):
                    wrong_translation = True
                    logger.error(
                        f"Block {mb.block_id}: WRONG TRANSLATION DETECTED - Backend returned generic response instead of translation!"
                    )
                    logger.error(
                        f"Block {mb.block_id}: Source: '{source_text_for_check[:80]}...'"
                    )
                    logger.error(
                        f"Block {mb.block_id}: Restored: '{restored[:80]}...'"
                    )
                    console.print(
                        f"[red]⚠⚠⚠ WRONG TRANSLATION for block {mb.block_id} - Backend returned generic response![/red]"
                    )
                    restore_errors.append("wrong_translation_generic_response")
                
                # Check for hallucination (backend adding content that wasn't in source)
                # For short blocks (headers/titles), translation should be roughly same length
                source_len = len(source_text_for_check.strip())
                restored_len = len(restored.strip())
                is_short_block = source_len < 100 or is_header_block or is_title_block
                
                if is_short_block and restored_len > source_len * 2.5:
                    # Translation is more than 2.5x longer - likely hallucination
                    # Check if translation contains source content
                    source_words = set(source_text_for_check.lower().split())
                    restored_words = set(restored.lower().split())
                    source_word_overlap = len(source_words & restored_words) / max(len(source_words), 1)
                    
                    # If translation is much longer but doesn't contain most source words, it's hallucination
                    if source_word_overlap < 0.3:  # Less than 30% word overlap
                        wrong_translation = True
                        logger.error(
                            f"Block {mb.block_id}: HALLUCINATION DETECTED - Backend added content that wasn't in source!"
                        )
                        logger.error(
                            f"Block {mb.block_id}: Source ({source_len} chars): '{source_text_for_check[:80]}...'"
                        )
                        logger.error(
                            f"Block {mb.block_id}: Restored ({restored_len} chars, {restored_len/source_len:.1f}x longer): '{restored[:150]}...'"
                        )
                        logger.error(
                            f"Block {mb.block_id}: Word overlap: {source_word_overlap:.1%}"
                        )
                        console.print(
                            f"[red]⚠⚠⚠ HALLUCINATION for block {mb.block_id} - Backend added {restored_len/source_len:.1f}x more content![/red]"
                        )
                        restore_errors.append("wrong_translation_hallucination")
                    elif restored_len > source_len * 3:
                        # Even with word overlap, if it's 3x longer, it's suspicious
                        logger.warning(
                            f"Block {mb.block_id}: Translation is {restored_len/source_len:.1f}x longer than source - may contain extra content"
                        )
                        console.print(
                            f"[yellow]⚠ Block {mb.block_id}: Translation is {restored_len/source_len:.1f}x longer - may have extra content[/yellow]"
                        )
                        restore_errors.append("translation_too_long")
                
                # Get block metadata for context-aware detection (reuse from earlier)
                # is_header_block and is_bullet_block already set above
                is_title_block = False
                block_type_meta = "normal"
                for page in doc.pages:
                    for block in page.blocks:
                        if block.id == mb.block_id:
                            block_type_meta = block.meta.get("block_type", "normal") if hasattr(block, 'meta') else "normal"
                            is_title_block = block_type_meta == "title"
                            break
                    if block.id == mb.block_id:
                        break

                # Use improved identity detection
                identity_result = check_identity_translation(
                    source_text_for_check,
                    restored,
                    is_header=is_header_block,
                    is_bullet=is_bullet_block,
                    is_title=is_title_block,
                    block_type=block_type_meta,
                )
                
                identity_translation = identity_result.is_identity
                
                if identity_translation:
                    if identity_result.should_retry:
                        logger.error(
                            f"Block {mb.block_id}: IDENTITY TRANSLATION DETECTED (confidence: {identity_result.confidence:.1%}) - {identity_result.reason}"
                        )
                        logger.error(
                            f"Block {mb.block_id}: Source: '{source_text_for_check[:80]}...'"
                        )
                        logger.error(
                            f"Block {mb.block_id}: Restored: '{restored[:80]}...'"
                        )
                        if identity_result.valid_identical_content:
                            logger.info(
                                f"Block {mb.block_id}: Valid identical content: {identity_result.valid_identical_content[:5]}"
                            )
                        console.print(
                            f"[red]⚠⚠⚠ IDENTITY TRANSLATION for block {mb.block_id} - {identity_result.reason}[/red]"
                        )
                        restore_errors.append("identity_translation")
                    else:
                        # Valid identical content - don't flag as error
                        logger.info(
                            f"Block {mb.block_id}: Text identical but valid ({identity_result.reason}) - ACCEPTING"
                        )
                        if identity_result.valid_identical_content:
                            logger.info(
                                f"Block {mb.block_id}: Valid identical content: {identity_result.valid_identical_content[:5]}"
                            )
                        identity_translation = False  # Clear flag since it's valid

            # Overall validation
            # A block is OK only if:
            # 1. Placeholders are preserved
            # 2. No restore errors
            # 3. Not an identity translation (output != input)
            # 4. Not a wrong translation (generic response)
            # 5. Translation is not empty
            ok = (
                placeholders_ok 
                and len(restore_errors) == 0 
                and not identity_translation
                and not wrong_translation
                and restored.strip() != ""
            )
            # #region agent log
            if is_header_block:
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"C","location":"pipeline.py:1031","message":"Header/title validation result","data":{"block_id":mb.block_id,"ok":ok,"placeholders_ok":placeholders_ok,"restore_errors":restore_errors,"identity_translation":identity_translation,"wrong_translation":wrong_translation,"restored_len":len(restored) if restored else 0,"restored_preview":restored[:50] if restored else "","source_preview":source_text[:50]}})+'\n')
            # #endregion

            # CRITICAL: ALWAYS retry identity translations and wrong translations
            # These mean the backend didn't translate properly - we MUST get an actual translation
            # SPECIAL: Headers/titles get EXTRA priority - they must be translated
            
            should_retry = False
            if wrong_translation:
                # FORCE retry for wrong translations (generic responses) - this is MANDATORY
                logger.warning(f"Block {mb.block_id}: Wrong translation (generic response) detected - retrying")
                console.print(f"[yellow]⚠️ Block {mb.block_id}: Generic response detected - retrying[/yellow]")
                should_retry = True
                if is_header_block:
                    logger.warning(f"Block {mb.block_id}: Header/title has generic response - retrying")
            elif identity_translation and identity_result.should_retry:
                # Use the improved identity detection result to decide if we should retry
                # The check_identity_translation function already determined if retry is needed
                logger.warning(f"Block {mb.block_id}: Identity translation detected (confidence: {identity_result.confidence:.1%}) - retrying")
                console.print(f"[yellow]⚠️ Block {mb.block_id}: Identity translation - retrying[/yellow]")
                should_retry = True
                if is_header_block:
                    logger.warning(f"Block {mb.block_id}: Header/title is identity - retrying")
            elif cfg.retry_failed and not cached_result and candidate.strip() != "":
                # CRITICAL: Always retry if placeholders are missing - this is a hard failure
                should_retry = not placeholders_ok
                if not placeholders_ok:
                    missing_phs = [ph for ph in mb.registry.keys() if ph not in candidate] if mb.registry else []
                    logger.warning(f"Block {mb.block_id}: Missing {len(missing_phs)} placeholders - forcing retry: {missing_phs[:3]}")
                    console.print(f"[red]⚠️ Missing placeholders - forcing retry: {missing_phs[:3] if missing_phs else 'unknown'}[/red]")
                # Headers always retry if they have any issues
                if is_header_block and not ok:
                    should_retry = True
                    logger.warning(f"Block {mb.block_id}: Header/title has issues - forcing retry")
                    console.print(f"[yellow]⚠️ Header/title block has issues - forcing retry[/yellow]")
            
            # #region agent log
            retry_reason = ""
            if wrong_translation:
                retry_reason = "wrong_translation"
            elif identity_translation:
                retry_reason = "identity_translation"
            elif not placeholders_ok:
                retry_reason = "placeholder_issue"
            elif is_header_block and not ok:
                retry_reason = "header_issue"
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"D","location":"pipeline.py:1163","message":"Retry decision","data":{"block_id":mb.block_id,"should_retry":should_retry,"retry_reason":retry_reason,"wrong_translation":wrong_translation,"identity_translation":identity_translation,"placeholders_ok":placeholders_ok,"is_header":is_header_block,"ok":ok}})+'\n')
            # #endregion
            
            if should_retry:
                retry_reason_str = ""
                if wrong_translation:
                    retry_reason_str = "generic response"
                elif identity_translation:
                    retry_reason_str = "identity translation"
                else:
                    retry_reason_str = "validation failed"
                
                console.print(
                    f"[yellow]  🔄 Retrying block {mb.block_id} ({retry_reason_str}) with stronger constraints...[/yellow]"
                )
                # Retry with lower temperature and explicit translation instruction
                retry_reason = ""
                placeholder_emphasis = ""
                if not placeholders_ok and mb.registry:
                    missing_phs = [ph for ph in mb.registry.keys() if ph not in candidate] if candidate.strip() else list(mb.registry.keys())[:3]
                    retry_reason = f"The previous translation MISSED {len(missing_phs)} placeholders: {missing_phs[:3]}. "
                    placeholder_emphasis = "\n🚨🚨🚨 PLACEHOLDER PRESERVATION FAILURE - CRITICAL 🚨🚨🚨\n"
                    placeholder_emphasis += f"The source text contains {len(mb.registry)} placeholders that MUST be preserved:\n"
                    for ph in list(mb.registry.keys())[:5]:
                        placeholder_emphasis += f"  - {ph}\n"
                    placeholder_emphasis += "YOU MUST include ALL of these placeholders in your translation EXACTLY as written.\n"
                    placeholder_emphasis += "DO NOT translate, modify, or remove placeholders - they are protected markers.\n"
                    placeholder_emphasis += "If you see <<PERSON_NAME_0001>> in source, you MUST include <<PERSON_NAME_0001>> in your output.\n"
                    placeholder_emphasis += "If you see ⟦MATH_INLINE_0002⟧ in source, you MUST include ⟦MATH_INLINE_0002⟧ in your output.\n"
                elif wrong_translation:
                    retry_reason = "The previous translation was a generic response (like 'Je suis ravi de vous aider'). "
                elif identity_translation:
                    retry_reason = "The previous translation was identical to the source text. "
                
                # Special prompt for headers/titles
                header_emphasis = ""
                if is_header_block:
                    header_emphasis = "\n🚨 THIS IS A HEADER/TITLE - EXTRA CRITICAL 🚨\n"
                    header_emphasis += "- Headers and titles MUST be translated - they are never optional.\n"
                    header_emphasis += "- If source is 'Section 1: Introduction', translate to target language but KEEP the number.\n"
                    header_emphasis += "- Example: 'Section 1: Introduction' (EN) → 'Section 1 : Introduction' (FR) - keep '1' and 'Section'.\n"
                    header_emphasis += "- Preserve ALL numbers, colons, and formatting exactly.\n"
                
                retry_prompt = (
                    system_prompt
                    + "\n\n⚠️ RETRY MODE - PREVIOUS ATTEMPT FAILED ⚠️\n"
                    + retry_reason
                    + placeholder_emphasis
                    + header_emphasis
                    + f"CRITICAL: You MUST translate from {cfg.source_lang.upper()} to {cfg.target_lang.upper()}.\n"
                    + "You MUST NOT return the source text unchanged.\n"
                    + "You MUST NOT return generic responses, greetings, or explanations.\n"
                    + "You MUST output ONLY the translated text in " + cfg.target_lang.upper() + " language.\n"
                    + "🚨 You MUST preserve ALL placeholders exactly as written - this is MANDATORY.\n"
                    + "You MUST preserve formatting (bullets only where source has them, no added hyphens to paragraphs).\n"
                    + "You MUST preserve section numbers EXACTLY (e.g., '1. ', '2)', 'Section 3:' - keep the number and format).\n"
                    + "For short text (headers, bullets, titles), translate EVERY word - do not skip anything.\n"
                    + "If you return the source text unchanged, a generic response, or miss placeholders, the translation will fail."
                )
                console.print(f"[dim]  📝 Reprompting with enhanced instructions (temp: {max(0.0, cfg.temperature - 0.2):.2f})[/dim]")
                retry_req = TranslateRequest(
                    text=mb.masked_text,
                    source_lang=cfg.source_lang,
                    target_lang=cfg.target_lang,
                    system_prompt=retry_prompt,
                    temperature=max(0.0, cfg.temperature - 0.2),
                    n_candidates=1,
                )
                
                # MULTI-BACKEND RETRY STRATEGY: If cascade_free failed, try individual backends
                retry_candidate = ""
                retry_succeeded = False
                
                # If using cascade_free and it failed, try individual backends
                if backend.name == "cascade_free":
                    console.print(f"[yellow]  🔄 cascade_free failed, trying individual backends for retry...[/yellow]")
                    logger.info(f"Block {mb.block_id}: cascade_free failed, trying individual backends...")
                    # Try backends in order: DeepSeek > Google > Ollama
                    fallback_backends = []
                    try:
                        from scitrans.translation.backends.deepseek_backend import DeepSeekBackend
                        import os
                        if os.getenv("DEEPSEEK_API_KEY"):
                            fallback_backends.append(("deepseek", DeepSeekBackend()))
                    except Exception:
                        pass
                    try:
                        from scitrans.translation.backends.google_backend import GoogleTranslateBackend
                        fallback_backends.append(("google", GoogleTranslateBackend()))
                    except Exception:
                        pass
                    try:
                        from scitrans.translation.backends.ollama_backend import OllamaBackend
                        import requests
                        try:
                            requests.get("http://localhost:11434/api/tags", timeout=2)
                            fallback_backends.append(("ollama", OllamaBackend(model="llama3.2")))
                        except Exception:
                            pass
                    except Exception:
                        pass
                    
                    # Try each fallback backend
                    for backend_name, fallback_be in fallback_backends:
                        try:
                            console.print(f"[dim]  🔄 Trying {backend_name} backend for retry...[/dim]")
                            logger.info(f"Block {mb.block_id}: Trying {backend_name} backend for retry...")
                            retry_res = fallback_be.translate(retry_req)
                            if retry_res.candidates and retry_res.candidates[0]:
                                retry_candidate = retry_res.candidates[0]
                                retry_preview = retry_candidate[:80] + "..." if len(retry_candidate) > 80 else retry_candidate
                                console.print(f"[dim]  → {backend_name} returned: '{retry_preview}'[/dim]")
                                # Validate it's different from source
                                if retry_candidate.strip():
                                    retry_normalized = " ".join(retry_candidate.strip().split()).lower()
                                    source_normalized = " ".join(source_text.strip().split()).lower()
                                    if retry_normalized != source_normalized:
                                        logger.info(f"Block {mb.block_id}: {backend_name} retry succeeded!")
                                        console.print(f"[green]  ✓ {backend_name} retry succeeded![/green]")
                                        retry_succeeded = True
                                        break
                                    else:
                                        console.print(f"[yellow]  ⚠ {backend_name} retry still identity, trying next...[/yellow]")
                        except Exception as e:
                            logger.warning(f"Block {mb.block_id}: {backend_name} retry failed: {e}")
                            console.print(f"[red]  ✗ {backend_name} retry failed: {e}[/red]")
                            continue
                
                # If fallback backends didn't work, or not using cascade_free, try original backend again
                if not retry_succeeded:
                    console.print(f"[dim]  🔄 Retrying with original backend ({backend.name})...[/dim]")
                    try:
                        retry_res = backend.translate(retry_req)
                        retry_candidate = retry_res.candidates[0] if retry_res.candidates else ""
                        if retry_candidate:
                            retry_preview = retry_candidate[:80] + "..." if len(retry_candidate) > 80 else retry_candidate
                            console.print(f"[dim]  → Original backend returned: '{retry_preview}'[/dim]")
                    except Exception as e:
                        logger.warning(f"Block {mb.block_id}: Original backend retry failed: {e}")
                        console.print(f"[red]  ✗ Original backend retry failed: {e}[/red]")
                        retry_candidate = ""

                # Only proceed if retry returned something
                if retry_candidate.strip():
                    try:
                        # Validate BEFORE restoration
                        retry_placeholders_ok = masker.placeholders_present(retry_candidate, mb.registry)
                        retry_restored, retry_restore_errors = masker.restore(
                            retry_candidate, mb.registry, tolerant=True
                        )
                        
                        # Check for identity translation again after retry using improved detector
                        retry_identity = False
                        if cfg.detect_identity_translation and retry_restored.strip():
                            source_text_for_check = ""
                            is_header_block_retry = False
                            is_bullet_block_retry = False
                            is_title_block_retry = False
                            block_type_meta_retry = "normal"
                            for page in doc.pages:
                                for block in page.blocks:
                                    if block.id == mb.block_id:
                                        source_text_for_check = _block_text(block)
                                        is_header_block_retry = block.meta.get("is_header", False) if hasattr(block, 'meta') else False
                                        block_type_meta_retry = block.meta.get("block_type", "normal") if hasattr(block, 'meta') else "normal"
                                        is_title_block_retry = block_type_meta_retry == "title"
                                        source_preview_retry = source_text_for_check.strip()[:10]
                                        is_bullet_block_retry = any(source_preview_retry.startswith(bullet) for bullet in ["•", "-", "*", "·"])
                                        break
                            
                            if source_text_for_check:
                                retry_identity_result = check_identity_translation(
                                    source_text_for_check,
                                    retry_restored,
                                    is_header=is_header_block_retry,
                                    is_bullet=is_bullet_block_retry,
                                    is_title=is_title_block_retry,
                                    block_type=block_type_meta_retry,
                                )
                                retry_identity = retry_identity_result.is_identity and retry_identity_result.should_retry
                                if retry_identity:
                                    retry_restore_errors.append("identity_translation")
                        
                        # Check if retry is actually different from source
                        retry_source_normalized = " ".join(source_text.strip().split()).lower()
                        retry_restored_normalized = " ".join(retry_restored.strip().split()).lower()
                        retry_is_different = retry_source_normalized != retry_restored_normalized
                        
                        # Retry is OK only if: placeholders OK, no errors, not identity, AND actually different
                        retry_ok = (
                            retry_placeholders_ok 
                            and len(retry_restore_errors) == 0 
                            and not retry_identity
                            and retry_is_different  # CRITICAL: Must be different from source
                        )
                        
                        if retry_ok:
                            candidate = retry_candidate
                            restored = retry_restored
                            restore_errors = retry_restore_errors
                            ok = True
                            identity_translation = False  # Reset identity flag since retry succeeded
                            res_meta["retried"] = True
                            logger.info(f"Block {mb.block_id}: Retry SUCCESS - got actual translation")
                            retry_restored_preview = retry_restored[:80] + "..." if len(retry_restored) > 80 else retry_restored
                            console.print(f"[green]  ✅ Retry SUCCESS - Translation: '{retry_restored_preview}'[/green]")
                        else:
                            logger.error(f"Block {mb.block_id}: Retry FAILED - still identity or invalid")
                            retry_restored_preview = retry_restored[:80] + "..." if len(retry_restored) > 80 else retry_restored
                            console.print(f"[red]  ✗ Retry FAILED - Still invalid: '{retry_restored_preview}'[/red]")
                            if retry_identity:
                                console.print(f"[red]    Reason: Identity translation detected[/red]")
                            if not retry_placeholders_ok:
                                console.print(f"[red]    Reason: Placeholders not preserved[/red]")
                            if not retry_is_different:
                                console.print(f"[red]    Reason: Translation identical to source[/red]")
                    except Exception as e:
                        logger.debug(f"Retry validation failed for block {mb.block_id}: {e}")
                    pass  # Keep original failed result

            # REAL-TIME SCORING: Score immediately after translation (before storing)
            # This allows us to retry low-quality translations automatically
            post_score = None
            if restored and restored.strip() and mb.registry:
                try:
                    # Get block metadata for scoring
                    is_header_for_score = is_header_block
                    is_title_for_score = is_title_block
                    is_bullet_for_score = is_bullet_block
                    
                    post_score = compute_post_translation_score(
                        block_id=mb.block_id,
                        source_text=mb.masked_text,
                        translated_text=restored,
                        registry=mb.registry,
                        errors=restore_errors if restore_errors else ([] if ok else ["validation_failed"]),
                        is_header=is_header_for_score,
                        is_title=is_title_for_score,
                        is_bullet=is_bullet_for_score,
                    )
                    
                    # Log score in terminal
                    score_color = "green" if post_score.overall_score >= 0.85 else "yellow" if post_score.overall_score >= 0.70 else "red"
                    console.print(f"[{score_color}]  📊 Quality Score: {post_score.overall_score:.1%} (P:{post_score.placeholder_score:.1%} N:{post_score.numeric_score:.1%} F:{post_score.format_score:.1%})[/{score_color}]")
                    
                    # AUTOMATIC RETRY: If score is low and not already retried, retry with stronger constraints
                    if post_score.overall_score < 0.75 and not res_meta.get("retried", False) and cfg.retry_failed:
                        logger.warning(f"Block {mb.block_id}: Low quality score ({post_score.overall_score:.1%}) - auto-retrying")
                        console.print(f"[yellow]  🔄 Low quality score ({post_score.overall_score:.1%}) - auto-retrying with stronger constraints...[/yellow]")
                        
                        # Get source text for retry
                        source_text_for_retry = ""
                        for page in doc.pages:
                            for block in page.blocks:
                                if block.id == mb.block_id:
                                    source_text_for_retry = _block_text(block)
                                    break
                            if source_text_for_retry:
                                break
                        
                        # Stronger retry prompt based on score issues
                        score_issues = []
                        if post_score.placeholder_score < 0.9:
                            score_issues.append("placeholder preservation")
                        if post_score.numeric_score < 0.8:
                            score_issues.append("numeric accuracy")
                        if post_score.format_score < 0.8:
                            score_issues.append("format preservation")
                        if post_score.fluency_score < 0.7:
                            score_issues.append("fluency")
                        
                        issues_str = ", ".join(score_issues) if score_issues else "quality"
                        retry_prompt_score = (
                            system_prompt
                            + f"\n\n⚠️ QUALITY RETRY MODE - Score was {post_score.overall_score:.1%} ⚠️\n"
                            + f"Previous translation had issues with: {issues_str}.\n"
                            + f"CRITICAL: You MUST improve translation quality.\n"
                            + f"- Preserve ALL placeholders exactly (score: {post_score.placeholder_score:.1%})\n"
                            + f"- Preserve ALL numbers exactly (score: {post_score.numeric_score:.1%})\n"
                            + f"- Preserve formatting (bullets, line breaks) (score: {post_score.format_score:.1%})\n"
                            + f"- Ensure fluent translation (score: {post_score.fluency_score:.1%})\n"
                            + f"Output ONLY the improved translated text in {cfg.target_lang.upper()}.\n"
                        )
                        
                        retry_req_score = TranslateRequest(
                            text=mb.masked_text,
                            source_lang=cfg.source_lang,
                            target_lang=cfg.target_lang,
                            system_prompt=retry_prompt_score,
                            temperature=max(0.0, cfg.temperature - 0.3),  # Lower temperature for quality
                            n_candidates=1,
                        )
                        
                        try:
                            retry_res_score = backend.translate(retry_req_score)
                            retry_candidate_score = retry_res_score.candidates[0] if retry_res_score.candidates else ""
                            
                            if retry_candidate_score.strip():
                                retry_placeholders_ok_score = masker.placeholders_present(retry_candidate_score, mb.registry)
                                retry_restored_score, retry_restore_errors_score = masker.restore(
                                    retry_candidate_score, mb.registry, tolerant=True
                                )
                                
                                # Score the retry
                                retry_post_score = compute_post_translation_score(
                                    block_id=mb.block_id,
                                    source_text=mb.masked_text,
                                    translated_text=retry_restored_score,
                                    registry=mb.registry,
                                    errors=retry_restore_errors_score if retry_restore_errors_score else [],
                                )
                                
                                # Only use retry if it's better
                                if retry_post_score.overall_score > post_score.overall_score and retry_placeholders_ok_score:
                                    candidate = retry_candidate_score
                                    restored = retry_restored_score
                                    restore_errors = retry_restore_errors_score
                                    post_score = retry_post_score
                                    ok = retry_post_score.overall_score >= 0.70  # Accept if score improved to at least 0.70
                                    res_meta["retried"] = True
                                    res_meta["score_retry"] = True
                                    logger.info(f"Block {mb.block_id}: Score retry SUCCESS - improved from {post_score.overall_score:.1%} to {retry_post_score.overall_score:.1%}")
                                    console.print(f"[green]  ✅ Score retry SUCCESS - improved to {retry_post_score.overall_score:.1%}[/green]")
                                else:
                                    logger.warning(f"Block {mb.block_id}: Score retry did not improve (old: {post_score.overall_score:.1%}, new: {retry_post_score.overall_score:.1%})")
                                    console.print(f"[yellow]  ⚠ Score retry did not improve quality[/yellow]")
                        except Exception as e:
                            logger.warning(f"Block {mb.block_id}: Score retry failed: {e}")
                            console.print(f"[red]  ✗ Score retry failed: {e}[/red]")
                except Exception as e:
                    logger.warning(f"Block {mb.block_id}: Failed to compute post-translation score: {e}")
                    # Continue without score if computation fails
            
            # Store score in metadata
            if post_score:
                res_meta["post_score"] = {
                    "overall_score": post_score.overall_score,
                    "placeholder_score": post_score.placeholder_score,
                    "numeric_score": post_score.numeric_score,
                    "format_score": post_score.format_score,
                    "fluency_score": post_score.fluency_score,
                    "fidelity_score": post_score.fidelity_score,
                    "needs_review": post_score.needs_review,
                    "needs_retry": post_score.needs_retry,
                    "confidence": post_score.confidence,
                }

            # Store translation result for EVERY block (whether retried or not)
            # CRITICAL: Always store something - use source text as fallback if translation is empty/invalid
            # This ensures NO blocks are omitted from the final PDF
            if not restored or not restored.strip():
                # Translation is empty - use source text as fallback
                final_translation = source_text
                logger.warning(f"Block {mb.block_id}: Translation is empty, using source text as fallback")
            elif not ok and (identity_translation or wrong_translation):
                # Translation failed validation - still use it but log warning
                # This ensures the block is rendered (even if it's wrong) rather than omitted
                final_translation = restored
                logger.warning(f"Block {mb.block_id}: Translation failed validation but storing anyway to prevent omission")
            else:
                # Translation is valid
                final_translation = restored
            
            translated_blocks.append(
                TranslatedBlock(
                    block_id=mb.block_id,
                    source_text=mb.masked_text,
                    translated_text=final_translation,  # Use source as fallback if needed
                    ok=ok,
                    errors=restore_errors if restore_errors else ([] if ok else ["validation_failed"]),
                    meta=res_meta,
                )
            )
            # CRITICAL: Always store translation (or source text as fallback) to ensure block is rendered
            # This prevents blocks from being omitted from the final PDF
            translations[mb.block_id] = final_translation
            # #region agent log
            if is_header_block:
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"D","location":"pipeline.py:1282","message":"Header/title stored in translations","data":{"block_id":mb.block_id,"ok":ok,"stored_len":len(restored) if restored else 0,"stored_preview":restored[:50] if restored else "","source_preview":source_text[:50]}})+'\n')
            # #endregion
            
            # DEBUG: Log final translation status
            stored_preview = restored[:60] + "..." if len(restored) > 60 else restored
            if ok:
                logger.info(f"Block {mb.block_id}: ✅ OK - Translation stored ({len(restored)} chars): '{stored_preview}'")
                logger.debug(f"Block {mb.block_id}: Full restored text: {restored}")
                console.print(f"[green]  ✅ Block {idx+1}/{len(masked_blocks)}: OK - '{stored_preview}'[/green]")
            else:
                error_msg = ", ".join(restore_errors) if restore_errors else "validation_failed"
                logger.error(f"Block {mb.block_id}: ❌ FAILED - Errors: {error_msg}")
                logger.error(f"Block {mb.block_id}: Source: '{source_text[:80]}...'")
                logger.error(f"Block {mb.block_id}: Restored: '{restored[:80]}...'")
                console.print(f"[red]  ✗ Block {idx+1}/{len(masked_blocks)}: FAILED - {error_msg}[/red]")
                if identity_translation:
                    logger.error(f"Block {mb.block_id}: This is an IDENTITY TRANSLATION - backend returned source text!")
                    console.print(f"[red]  ⚠️ IDENTITY TRANSLATION detected![/red]")
            # NO CONTEXT BUFFER - Don't maintain context (user doesn't care)
            # NO TRANSLATION MEMORY - Don't save translations (always fresh)
    
    # Summary of translation results
    num_ok = sum(1 for tb in translated_blocks if tb.ok)
    num_failed = sum(1 for tb in translated_blocks if not tb.ok)
    logger.info(f"Translation summary: {num_ok} OK, {num_failed} failed out of {len(translated_blocks)} blocks")
    console.print(f"[cyan]Translation complete: {num_ok}/{len(translated_blocks)} blocks OK, {num_failed} failed[/cyan]")
    
    # Log error summary
    if num_failed > 0:
        error_types = {}
        for tb in translated_blocks:
            if not tb.ok and tb.errors:
                for error in tb.errors:
                    error_types[error] = error_types.get(error, 0) + 1
            if error_types:
                error_summary = ", ".join(f"{k}: {v}" for k, v in error_types.items())
                logger.warning(f"Translation errors: {error_summary}")
                console.print(f"[yellow]⚠ Translation errors: {error_summary}[/yellow]")

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
        # Get block metadata for scoring
        is_header_for_post = False
        is_title_for_post = False
        is_bullet_for_post = False
        for page in doc.pages:
            for block in page.blocks:
                if block.id == tb.block_id:
                    is_header_for_post = block.meta.get("is_header", False) if hasattr(block, 'meta') else False
                    block_type_post = block.meta.get("block_type", "normal") if hasattr(block, 'meta') else "normal"
                    is_title_for_post = block_type_post == "title"
                    source_text_post = _block_text(block)
                    source_preview_post = source_text_post.strip()[:10] if source_text_post else ""
                    is_bullet_for_post = any(source_preview_post.startswith(bullet) for bullet in ["•", "-", "*", "·"])
                    break
            if is_header_for_post or is_title_for_post:
                break
        
        post_score = compute_post_translation_score(
            block_id=tb.block_id,
            source_text=tb.source_text,
            translated_text=tb.translated_text,
            registry=mb.registry,
            errors=tb.errors,
            is_header=is_header_for_post,
            is_title=is_title_for_post,
            is_bullet=is_bullet_for_post,
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
    all_block_info = {}  # Store block info for debugging
    for page in doc.pages:
        for block in page.blocks:
            if block.type == "text":
                all_block_ids.add(block.id)
                source_text = _block_text(block)
                all_block_info[block.id] = {
                    "page": page,
                    "source_preview": source_text[:50] if source_text else "",
                    "is_header": block.meta.get("is_header", False) if hasattr(block, 'meta') else False,
                }
    
    missing_blocks = all_block_ids - set(translations.keys())
    if missing_blocks:
        logger.error(f"⚠️ {len(missing_blocks)} blocks have NO translation - using source text as fallback")
        console.print(f"[red]⚠️ ERROR: {len(missing_blocks)} blocks missing translations - using source text[/red]")
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            missing_info = []
            for bid in list(missing_blocks)[:10]:
                block_info = all_block_info.get(bid, {})
                missing_info.append({
                    "block_id": bid,
                    "source_preview": block_info.get("source_preview", ""),
                    "is_header": block_info.get("is_header", False),
                })
            f.write(json.dumps({"sessionId":"debug-session","runId":"quality-test","hypothesisId":"H","location":"pipeline.py:1731","message":"Missing blocks detected","data":{"missing_count":len(missing_blocks),"total_blocks":len(all_block_ids),"translated_count":len(translations),"missing_blocks":missing_info}})+'\n')
        # #endregion
        # CRITICAL FIX: Use source text as fallback for ALL missing blocks
        for bid in missing_blocks:
            # Find the block to see what text it has
            source_text = ""
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == bid:
                        source_text = _block_text(block)
                        # Use source as fallback (better than omitting the block)
                        translations[bid] = source_text
                        logger.error(f"  Using source text as fallback for block {bid}: '{source_text[:60]}...'")
                        console.print(f"[red]  Using source as fallback for block {bid}[/red]")
                        break
                if source_text:
                    break
            if not source_text:
                # Block not found - this is a serious issue
                logger.error(f"  Block {bid} not found in document - this should not happen!")
                console.print(f"[red]  Block {bid} not found in document![/red]")
    
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
        logger.error(f"❌ {len(missing_masked)} masked blocks have NO translation!")
        console.print(f"[red]❌ ERROR: {len(missing_masked)} masked blocks missing translations![/red]")
        for bid in list(missing_masked)[:5]:
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == bid:
                        source_text = _block_text(block)
                        is_header = block.meta.get("is_header", False)
                        block_type = block.meta.get("block_type", "normal")
                        logger.error(f"  Missing block {bid} ({block_type}): '{source_text[:60]}...'")
                        console.print(f"[red]  Missing {block_type}: {bid} - '{source_text[:40]}...'[/red]")
                        break
    
    # Validate headers/titles were translated
    header_block_ids = set()
    for page in doc.pages:
        for block in page.blocks:
            if block.type == "text" and block.meta.get("is_header"):
                header_block_ids.add(block.id)
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    block_type = block.meta.get("block_type", "header")
                    source_text = _block_text(block)
                    trans_text = translations.get(block.id, "")
                    f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"E","location":"pipeline.py:1455","message":"Header/title found in document","data":{"block_id":block.id,"block_type":block_type,"has_translation":block.id in translations,"source_preview":source_text[:50],"trans_preview":trans_text[:50] if trans_text else ""}})+'\n')
                # #endregion
    
    missing_headers = header_block_ids - set(translations.keys())
    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"post-fix","hypothesisId":"E","location":"pipeline.py:1464","message":"Header/title validation summary","data":{"total_headers":len(header_block_ids),"missing_headers":len(missing_headers),"missing_ids":list(missing_headers)[:10]}})+'\n')
    # #endregion
    if missing_headers:
        logger.error(f"❌ {len(missing_headers)} headers/titles missing translations!")
        console.print(f"[red]❌ ERROR: {len(missing_headers)} headers/titles not translated![/red]")
        # Try to fix by using source text as fallback (better than nothing)
        for bid in missing_headers:
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == bid:
                        source_text = _block_text(block)
                        # Use source as fallback (will be marked as identity but at least present)
                        translations[bid] = source_text
                        logger.warning(f"  Using source text as fallback for header {bid}: '{source_text[:50]}...'")
                        console.print(f"[yellow]  Using source as fallback for header {bid}[/yellow]")
                        break
                if block.id == bid:
                    break
    else:
        # Check if headers have proper translations (not identity)
        failed_headers = []
        for bid in header_block_ids:
            trans_text = translations.get(bid, "")
            if trans_text:
                # Check if it's an identity translation
                for page in doc.pages:
                    for block in page.blocks:
                        if block.id == bid:
                            source_text = _block_text(block)
                            source_norm = " ".join(source_text.strip().split()).lower()
                            trans_norm = " ".join(trans_text.strip().split()).lower()
                            if source_norm == trans_norm:
                                failed_headers.append((bid, source_text[:50]))
                            break
                    if block.id == bid:
                        break
        
        if failed_headers:
            logger.warning(f"⚠️ {len(failed_headers)} headers/titles are identity translations (not properly translated)")
            console.print(f"[yellow]⚠️ WARNING: {len(failed_headers)} headers/titles are identity translations[/yellow]")
            for bid, src in failed_headers[:3]:
                logger.warning(f"  Header {bid}: '{src}...' (not translated)")
                console.print(f"[yellow]  Header {bid}: '{src[:40]}...' (not translated)[/yellow]")
            else:
                logger.info(f"✅ All {len(header_block_ids)} headers/titles have proper translations")
            if header_block_ids:
                console.print(f"[green]✓ All {len(header_block_ids)} headers/titles translated[/green]")
    
    # Validate and FIX numbering preservation
    # Note: 're' is already imported at module level (line 5)
    numbering_issues = []
    numbering_fixes = {}
    
    for mb in masked_blocks:
        # Get source block
        source_text = ""
        source_block = None
        for page in doc.pages:
            for block in page.blocks:
                if block.id == mb.block_id:
                    source_text = _block_text(block)
                    source_block = block
                    break
        
        if not source_text or not source_block:
            continue
        
        translated_text = translations.get(mb.block_id, "")
        if not translated_text:
            continue
        
        # Enhanced numbering detection using NumberingDetector
        from scitrans.utils.numbering_detector import NumberingDetector
        source_numbering = NumberingDetector.detect_numbering(source_text)
        
        if source_numbering:
            # Extract the numbering prefix from source
            numbering_prefix, numbering_type, _ = source_numbering
            source_match = re.match(r'^((?:\d+[\.\)]|Section\s+\d+|Chapter\s+\d+|[IVXLCDM]+[\.\)]|[a-zA-Z][\.\)]|\d+\.\d+)[:\s]*)', source_text, re.IGNORECASE)
            if source_match:
                source_numbering = source_match.group(1)  # e.g., "1. ", "Section 2: "
                source_num_match = re.search(r'(\d+)', source_numbering)
                source_num = source_num_match.group(1) if source_num_match else None
                
                # Check if translation preserved the number
                if source_num:
                    # Check if same number appears in translation (more flexible)
                    if source_num not in translated_text:
                        # Try to fix it by prepending the numbering
                        # Extract the text part after numbering
                        text_after_numbering = source_text[len(source_numbering):].strip()
                        # Try to find similar text in translation
                        if text_after_numbering and len(text_after_numbering) > 3:
                            # If translation starts with the text (without number), add the number
                            trans_stripped = translated_text.strip()
                            if trans_stripped.startswith(text_after_numbering[:10]) or text_after_numbering[:10] in trans_stripped:
                                # Translation lost the number - restore it
                                fixed_translation = source_numbering + trans_stripped
                                numbering_fixes[mb.block_id] = fixed_translation
                                logger.info(f"Block {mb.block_id}: Restoring lost section number: '{source_numbering}'")
                                console.print(f"[yellow]🔧 Block {mb.block_id}: Restoring section number[/yellow]")
                            else:
                                # Number is missing but text doesn't match - log as issue
                                numbering_issues.append((mb.block_id, source_text[:50], translated_text[:50]))
                    else:
                        # Number exists, but check if format is preserved
                        trans_match = re.match(r'^((?:\d+[\.\)]|Section\s+\d+|Chapter\s+\d+)[:\s]*)', translated_text, re.IGNORECASE)
                        if not trans_match:
                            # Number exists but format might be different - check if it's at the start
                            if not translated_text.strip().startswith(source_num):
                                numbering_issues.append((mb.block_id, source_text[:50], translated_text[:50]))
    
    # Apply numbering fixes
    if numbering_fixes:
        logger.info(f"🔧 Applying {len(numbering_fixes)} numbering fixes...")
        console.print(f"[yellow]🔧 Fixing {len(numbering_fixes)} blocks with lost section numbers...[/yellow]")
        for block_id, fixed_text in numbering_fixes.items():
            translations[block_id] = fixed_text
            # Update the translated block too (create new instance since TranslatedBlock is frozen)
            for idx, tb in enumerate(translated_blocks):
                if tb.block_id == block_id:
                    # Create a new TranslatedBlock with updated text (can't modify frozen instance)
                    updated_tb = TranslatedBlock(
                        block_id=tb.block_id,
                        source_text=tb.source_text,
                        translated_text=fixed_text,
                        ok=tb.ok,
                        errors=tb.errors,
                        meta=tb.meta,
                    )
                    translated_blocks[idx] = updated_tb
                    break
    
    if numbering_issues:
        logger.warning(f"⚠️ {len(numbering_issues)} blocks may have lost section numbering (could not auto-fix)")
        console.print(f"[yellow]⚠️ WARNING: {len(numbering_issues)} blocks may have lost section numbers[/yellow]")
        for bid, src, trans in numbering_issues[:3]:
            logger.warning(f"  Block {bid}: Source '{src}...' → Translation '{trans}...'")
            console.print(f"[yellow]  Block {bid}: '{src[:40]}...' → '{trans[:40]}...'[/yellow]")
    else:
        logger.info("✅ Section numbering appears preserved in translations")
        if numbering_fixes:
            console.print(f"[green]✓ Fixed {len(numbering_fixes)} blocks with restored section numbers[/green]")
    
    # Check for missing translations
    missing_masked = [mb.block_id for mb in masked_blocks if mb.block_id not in translations]
    if missing_masked:
        logger.warning(f"⚠️ {len(missing_masked)} MASKED blocks have NO translation - using source text as fallback")
        console.print(f"[yellow]⚠️ WARNING: {len(missing_masked)} masked blocks missing - using source text[/yellow]")
        # CRITICAL FIX: Use source text as fallback for masked blocks that failed translation
        for bid in missing_masked:
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == bid:
                        source_text = _block_text(block)
                        translations[bid] = source_text
                        logger.warning(f"  Using source text as fallback for masked block {bid}: '{source_text[:60]}...'")
                        console.print(f"[yellow]  Using source as fallback for masked block {bid}[/yellow]")
                        break
                if block.id == bid:
                    break

    # 4) Render - select renderer based on mode
    logger.info(f"Rendering translated PDF to: {output_pdf}")
    console.print(f"[cyan]📄 Rendering translated PDF...[/cyan]")
    try:
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
        )
        else:
            raise ValueError(
                f"Invalid render_mode: {cfg.render_mode}. Must be 'perfect', 'enhanced', 'auto', 'math-aware', or 'math-safe'."
            )
        
        # Verify the PDF was created
        if not Path(output_pdf).exists():
            raise FileNotFoundError(f"Rendered PDF was not created: {output_pdf}")
        pdf_size = Path(output_pdf).stat().st_size
        logger.info(f"✅ Rendered PDF created: {output_pdf} ({pdf_size} bytes)")
        console.print(f"[green]✅ Rendered PDF created: {Path(output_pdf).name} ({pdf_size} bytes)[/green]")
        
        # Also save a copy of the output PDF in the artifacts directory for convenience
        import shutil
        artifacts_pdf = out_dir / Path(output_pdf).name
        try:
            shutil.copy2(output_pdf, artifacts_pdf)
            logger.info(f"Saved output PDF copy to artifacts: {artifacts_pdf}")
            console.print(f"[green]✓ Output PDF also saved to artifacts: {artifacts_pdf}[/green]")
        except Exception as e:
            logger.warning(f"Could not copy output PDF to artifacts directory: {e}")
    except Exception as e:
        logger.error(f"Rendering failed: {e}", exc_info=True)
        console.print(f"[red]❌ Rendering failed: {e}[/red]")
        raise

    # 4.1) Validate rendered PDF for overlaps (CRITICAL: ensure no overlapping text)
    logger.info("Validating rendered PDF for overlapping text blocks...")
    rendered_overlap_metrics = {}
    for page_idx in range(len(doc.pages)):
        try:
            rendered_metrics = compute_rendered_pdf_overlap_metrics(output_pdf, page_index=page_idx)
            rendered_overlap_metrics[f"page_{page_idx + 1}"] = {
                "overlap_pairs": rendered_metrics.overlap_pairs,
                "mean_iou": rendered_metrics.mean_iou,
            }
            if rendered_metrics.overlap_pairs > 0:
                logger.warning(
                    f"⚠️ Page {page_idx + 1}: Found {rendered_metrics.overlap_pairs} overlapping text block pairs "
                    f"(mean IoU: {rendered_metrics.mean_iou:.3f})"
                )
                console.print(
                    f"[yellow]⚠️ Page {page_idx + 1}: {rendered_metrics.overlap_pairs} overlapping blocks detected![/yellow]"
                )
            else:
                logger.info(f"✅ Page {page_idx + 1}: No overlapping text blocks")
        except Exception as e:
            logger.warning(f"Could not validate overlaps for page {page_idx + 1}: {e}")
    
    # Store rendered overlap metrics
    (out_dir / "rendered_overlap_metrics.json").write_text(
        json.dumps(rendered_overlap_metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    
    # Also save a copy of the output PDF in the artifacts directory for convenience
    import shutil
    artifacts_pdf = out_dir / Path(output_pdf).name
    try:
        shutil.copy2(output_pdf, artifacts_pdf)
        logger.info(f"Saved output PDF copy to artifacts: {artifacts_pdf}")
        console.print(f"[green]✓ Output PDF also saved to: {artifacts_pdf}[/green]")
    except Exception as e:
        logger.warning(f"Could not copy output PDF to artifacts directory: {e}")

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
        "rendered_overlap": rendered_overlap_metrics,
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
