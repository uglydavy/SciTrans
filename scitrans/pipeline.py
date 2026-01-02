from __future__ import annotations

import json
import logging
import re
import time
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
    progress: Optional[Any] = None,
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

    # 2) Mask - Extract ALL text blocks (headers, titles, paragraphs, numbering, etc.)
    masker = MaskingEngine()
    masked_blocks: list[MaskedBlock] = []
    skipped_blocks = []
    total_text_blocks = 0
    header_count = 0
    title_count = 0
    
    for page in doc.pages:
        for block in page.blocks:
            if block.type != "text":
                continue
            total_text_blocks += 1
            # PHASE 4: Preserve tables unless explicitly translating
            if block.meta.get("region") == "table" and not cfg.translate_tables:
                skipped_blocks.append((block.id, "table"))
                logger.debug(f"Skipping table block {block.id}")
                continue
            src = _block_text(block)
            # Skip empty blocks
            if not src.strip():
                skipped_blocks.append((block.id, "empty"))
                logger.debug(f"Skipping empty block {block.id}")
                continue
            
            # Log headers/titles for visibility
            if block.meta.get("is_header"):
                block_type = block.meta.get("block_type", "header")
                if block_type == "title":
                    title_count += 1
                    logger.debug(f"Detected TITLE block {block.id}: '{src[:50]}...'")
                else:
                    header_count += 1
                    logger.debug(f"Detected HEADER block {block.id}: '{src[:50]}...'")
            # Pass block to masker for advanced span-level math detection
            masked, registry, counts = masker.mask(src, block=block)
            masked_blocks.append(
                MaskedBlock(
                    block_id=block.id, masked_text=masked, registry=registry, mask_counts=counts
                )
            )
    
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

    logger.info(f"Starting translation of {len(masked_blocks)} blocks...")
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
    
    for idx, mb in enumerate(masked_blocks):  # Get pre-score for adaptive strategy
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

        # Get block metadata for enhanced prompting
        is_header_block = False
        is_bullet_block = False
        for page in doc.pages:
            for block in page.blocks:
                if block.id == mb.block_id:
                    is_header_block = block.meta.get("is_header", False)
                    # Check if it's a bullet point
                    source_text_check = _block_text(block)
                    is_bullet_block = any(source_text_check.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"])
                    break
        
        # Build enhanced prompt for headers/bullets
        enhanced_prompt = build_system_prompt(
            source=cfg.source_lang,
            target=cfg.target_lang,
            glossary=glossary,
            is_header=is_header_block,
            is_bullet=is_bullet_block,
        )
        
        # Always translate - no cache, no memory, no context
        # Translate each block independently
        req = TranslateRequest(
            text=mb.masked_text,
            source_lang=cfg.source_lang,
            target_lang=cfg.target_lang,
            system_prompt=enhanced_prompt,  # Use enhanced prompt
            temperature=block_temperature,
            n_candidates=block_n_candidates,
            context="",  # No context - user doesn't care about context retention
        )

        # DEBUG: Log what we're sending to backend
        masked_preview = mb.masked_text[:80] + "..." if len(mb.masked_text) > 80 else mb.masked_text
        logger.info(f"Block {mb.block_id}: Sending to backend (masked, {len(mb.masked_text)} chars): {masked_preview}")
        logger.debug(f"Block {mb.block_id}: Full masked text: {mb.masked_text}")

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

        # Rerank candidates if enabled and multiple candidates
        if cfg.enable_reranking and len(candidates) > 1:
            # Get source text for reranking (unmasked)
            source_text_for_rerank = mb.masked_text
            # Find original source text from document
            is_header_for_rerank = False
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text_for_rerank = _block_text(block)
                        is_header_for_rerank = block.meta.get("is_header", False)
                        break

            ranked = rerank_candidates(
                candidates=candidates,
                source_text=source_text_for_rerank,
                registry=mb.registry,
                glossary=glossary,
                is_header=is_header_for_rerank,  # Pass header flag for enhanced scoring
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
        identity_translation = False
        wrong_translation = False
        if restored.strip():
            # Use the source_text we already have from earlier in the loop (line 226)
            source_text_for_check = source_text
            
            # STRICT comparison: normalized whitespace, case-insensitive
            source_normalized = " ".join(source_text_for_check.strip().split()).lower()
            restored_normalized = " ".join(restored.strip().split()).lower()
            
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
            
            # Check if they're identical
            if source_normalized == restored_normalized:
                # SMART CHECK: Some words are identical in both languages (e.g., "Introduction", "Section", numbers)
                # If the text is short and contains only common identical words, accept it as valid
                identical_words_en_fr = {
                    "introduction", "section", "chapter", "part", "abstract", "conclusion",
                    "methodology", "results", "discussion", "references", "appendix",
                    "figure", "table", "equation", "algorithm", "theorem", "lemma",
                    "proof", "definition", "example", "note", "remark", "corollary",
                    "proposition", "hypothesis", "experiment", "analysis", "evaluation"
                }
                
                # Extract words (remove numbers, punctuation, placeholders)
                source_words = set(re.findall(r'\b[a-z]+\b', source_normalized))
                restored_words = set(re.findall(r'\b[a-z]+\b', restored_normalized))
                
                # Check if all words are identical in both languages OR the text is very short (likely a header)
                all_words_identical = source_words == restored_words and all(
                    word in identical_words_en_fr for word in source_words
                )
                is_short_header = len(source_normalized) < 50 and len(source_words) <= 5
                
                if all_words_identical or (is_short_header and source_words == restored_words):
                    # Valid - words are the same in both languages (e.g., "1. Introduction" -> "1. Introduction")
                    logger.info(
                        f"Block {mb.block_id}: Text identical but contains words same in both languages - ACCEPTING as valid"
                    )
                    identity_translation = False  # Don't flag as error
                else:
                    identity_translation = True
                    logger.error(
                        f"Block {mb.block_id}: IDENTITY TRANSLATION DETECTED - Backend returned source text unchanged!"
                    )
                    logger.error(
                        f"Block {mb.block_id}: Source: '{source_text_for_check[:80]}...'"
                    )
                    logger.error(
                        f"Block {mb.block_id}: Restored: '{restored[:80]}...'"
                    )
                console.print(
                        f"[red]⚠⚠⚠ IDENTITY TRANSLATION for block {mb.block_id} - Source and translation are IDENTICAL![/red]"
                )
                restore_errors.append("identity_translation")
            elif len(source_normalized) > 10 and len(restored_normalized) > 10:
                # Check similarity - but be more lenient for short text or headers
                # Short headers/titles often have high similarity even when translated correctly
                is_short_text = len(source_normalized) < 30
                is_header = block.meta.get("is_header", False) if hasattr(block, 'meta') else False
                
                try:
                    from rapidfuzz import fuzz
                    similarity = fuzz.ratio(source_normalized, restored_normalized)
                    # Only flag as identity if very high similarity AND not a short header
                    # Headers like "Introduction" -> "Introduction" are valid (same word in both languages)
                    if similarity > 95 and not (is_short_text or is_header):  # Stricter threshold, skip short/headers
                        identity_translation = True
                        logger.warning(
                            f"Block {mb.block_id}: HIGH SIMILARITY ({similarity:.1f}%) - Possible identity translation"
                        )
                        restore_errors.append("identity_translation_high_similarity")
                    elif similarity > 90 and not (is_short_text or is_header):
                        # Log but don't fail - might be legitimate
                        logger.debug(f"Block {mb.block_id}: Moderate similarity ({similarity:.1f}%) - monitoring")
                except ImportError:
                    # rapidfuzz not available, skip similarity check
                    pass

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

        # Check if this is a header/title block (for special handling)
        is_header_block = False
        for page in doc.pages:
            for block in page.blocks:
                if block.id == mb.block_id and block.meta.get("is_header"):
                    is_header_block = True
                    break
            if is_header_block:
                break
        
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
        elif identity_translation:
            # Only retry identity translations if they're NOT valid identical words
            # Check if it's a valid case (short header with identical words in both languages)
            source_words = set(re.findall(r'\b[a-z]+\b', source_normalized))
            restored_words = set(re.findall(r'\b[a-z]+\b', restored_normalized))
            identical_words_en_fr = {
                "introduction", "section", "chapter", "part", "abstract", "conclusion",
                "methodology", "results", "discussion", "references", "appendix"
            }
            all_words_identical = source_words == restored_words and all(
                word in identical_words_en_fr for word in source_words
            )
            
            if not all_words_identical:
                # Real identity translation - retry
                logger.warning(f"Block {mb.block_id}: Identity translation detected - retrying")
                console.print(f"[yellow]⚠️ Block {mb.block_id}: Identity translation - retrying[/yellow]")
                should_retry = True
                if is_header_block:
                    logger.warning(f"Block {mb.block_id}: Header/title is identity - retrying")
            else:
                # Valid identical words - don't retry, just log
                logger.info(f"Block {mb.block_id}: Text identical but contains words same in both languages - OK")
                identity_translation = False  # Clear the flag since it's valid
        elif cfg.retry_failed and not cached_result and candidate.strip() != "":
            # Also retry for placeholder issues if retry is enabled
            should_retry = not placeholders_ok
            # Headers always retry if they have any issues
            if is_header_block and not ok:
                should_retry = True
                logger.warning(f"Block {mb.block_id}: Header/title has issues - forcing retry")
                console.print(f"[yellow]⚠️ Header/title block has issues - forcing retry[/yellow]")
        
        if should_retry:
            console.print(
                f"[yellow]Retrying block {mb.block_id} with stronger constraints[/yellow]"
            )
            # Retry with lower temperature and explicit translation instruction
            retry_reason = ""
            if wrong_translation:
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
                + header_emphasis
                + f"CRITICAL: You MUST translate from {cfg.source_lang.upper()} to {cfg.target_lang.upper()}.\n"
                + "You MUST NOT return the source text unchanged.\n"
                + "You MUST NOT return generic responses, greetings, or explanations.\n"
                + "You MUST output ONLY the translated text in " + cfg.target_lang.upper() + " language.\n"
                + "You MUST preserve ALL placeholders exactly as written.\n"
                + "You MUST preserve formatting (bullets only where source has them, no added hyphens to paragraphs).\n"
                + "You MUST preserve section numbers EXACTLY (e.g., '1. ', '2)', 'Section 3:' - keep the number and format).\n"
                + "For short text (headers, bullets, titles), translate EVERY word - do not skip anything.\n"
                + "If you return the source text unchanged or a generic response, the translation will fail."
            )
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
                        logger.info(f"Block {mb.block_id}: Trying {backend_name} backend for retry...")
                        retry_res = fallback_be.translate(retry_req)
                        if retry_res.candidates and retry_res.candidates[0]:
                            retry_candidate = retry_res.candidates[0]
                            # Validate it's different from source
                            if retry_candidate.strip():
                                retry_normalized = " ".join(retry_candidate.strip().split()).lower()
                                source_normalized = " ".join(source_text.strip().split()).lower()
                                if retry_normalized != source_normalized:
                                    logger.info(f"Block {mb.block_id}: {backend_name} retry succeeded!")
                                    retry_succeeded = True
                                    break
                    except Exception as e:
                        logger.warning(f"Block {mb.block_id}: {backend_name} retry failed: {e}")
                        continue
            
            # If fallback backends didn't work, or not using cascade_free, try original backend again
            if not retry_succeeded:
                try:
                    retry_res = backend.translate(retry_req)
                    retry_candidate = retry_res.candidates[0] if retry_res.candidates else ""
                except Exception as e:
                    logger.warning(f"Block {mb.block_id}: Original backend retry failed: {e}")
                    retry_candidate = ""

            # Only proceed if retry returned something
            if retry_candidate.strip():
                try:
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
                        console.print(f"[green]✓ Block {mb.block_id}: Retry succeeded - translation is different from source[/green]")
                    else:
                        logger.error(f"Block {mb.block_id}: Retry FAILED - still identity or invalid")
                        console.print(f"[red]✗ Block {mb.block_id}: Retry failed - still identity translation[/red]")
                except Exception as e:
                    logger.debug(f"Retry validation failed for block {mb.block_id}: {e}")
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
    
    missing_headers = header_block_ids - set(translations.keys())
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
        logger.error(f"❌ {len(missing_masked)} MASKED blocks have NO translation stored!")
        console.print(f"[red]❌ CRITICAL: {len(missing_masked)} masked blocks missing from translations dict![/red]")

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
