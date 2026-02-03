from __future__ import annotations

import json
import random
import logging
import re
import threading
import time
import hashlib
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
from scitrans.parsing.layout import is_table_candidate
from scitrans.rendering.math_aware_renderer import (
    MathAwareRenderConfig,
    render_translated_pdf_math_aware,
)
from scitrans.rendering.math_safe_renderer import RenderConfig
from scitrans.rendering.perfect_renderer import render_translated_pdf_perfect
from scitrans.translation.backends.base import TranslateRequest, TranslationBackend
from scitrans.translation.cache import TranslationCache, make_cache_key
from scitrans.translation.memory import TranslationMemory
from scitrans.translation.prompting import build_system_prompt, get_prompt_version
from scitrans.translation.reranking import rerank_candidates
from scitrans.utils.identity_translation_detector import (
    check_identity_translation,
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
    # Renderer mode: "perfect" (primary), "auto"/"math-aware" (equation preservation)
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
    cache_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days
    use_memory: bool = True
    memory_file: str = "outputs/translation_memory.json"
    memory_min_similarity: float = 0.92
    memory_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days
    memory_use_fuzzy: bool = True


def _block_text(block) -> str:
    # Preserve line breaks from PDF extraction.
    lines = []
    for ln in block.lines:
        lines.append("".join(sp.text for sp in ln.spans))
    return "\n".join(lines).strip("\n")


def _compute_cache_version(
    *,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    system_prompt: str,
) -> str:
    render_cfg = cfg.render.__dict__.copy()
    version_data = {
        "backend": backend.name,
        "model": getattr(backend, "model", cfg.model),
        "source_lang": cfg.source_lang,
        "target_lang": cfg.target_lang,
        "system_prompt": system_prompt,
        "render": render_cfg,
        "render_mode": cfg.render_mode,
        "translate_tables": cfg.translate_tables,
    }
    payload = json.dumps(version_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def extract_section_prefix(text: str) -> tuple[str, str]:
    """Extract section/chapter prefix from text.
    
    Returns:
        (prefix, content) where prefix is "Section X: " and content is the rest
        
    Examples:
        "Section 1: Introduction" -> ("Section 1: ", "Introduction")
        "Chapter 3: Methods" -> ("Chapter 3: ", "Methods")
        "Normal text" -> ("", "Normal text")
    """
    pattern = r'^(Section|Chapter|Part|Chapitre|Partie)\s+(\d+[.\)]?)\s*:?\s*'
    match = re.match(pattern, text, re.IGNORECASE)
    if match:
        prefix = match.group(0)  # e.g., "Section 1: "
        content = text[len(prefix):].strip()  # Rest of text
        return prefix, content
    return "", text


def translate_section_prefix(prefix: str, target_lang: str) -> str:
    """Translate section prefix while preserving number.
    
    Args:
        prefix: e.g., "Section 1: ", "Chapter 3: "
        target_lang: Target language code
        
    Returns:
        Translated prefix with number preserved, e.g., "Section 1 : ", "Chapitre 3 : "
    """
    if not prefix:
        return ""
    
    # Extract the keyword and number
    pattern = r'^(Section|Chapter|Part|Chapitre|Partie)\s+(\d+[.\)]?)\s*:?\s*'
    match = re.match(pattern, prefix, re.IGNORECASE)
    if not match:
        return prefix
    
    keyword = match.group(1)
    number = match.group(2)
    
    # Simple translation map for common keywords
    keyword_map = {
        # English to French
        "section": {"fr": "Section", "es": "Sección", "de": "Abschnitt"},
        "chapter": {"fr": "Chapitre", "es": "Capítulo", "de": "Kapitel"},
        "part": {"fr": "Partie", "es": "Parte", "de": "Teil"},
        # French to other
        "chapitre": {"en": "Chapter", "es": "Capítulo", "de": "Kapitel"},
        "partie": {"en": "Part", "es": "Parte", "de": "Teil"},
    }
    
    keyword_lower = keyword.lower()
    if keyword_lower in keyword_map and target_lang in keyword_map[keyword_lower]:
        translated_keyword = keyword_map[keyword_lower][target_lang]
    else:
        # Preserve original if no mapping
        translated_keyword = keyword
    
    # Return formatted prefix with French spacing for colons
    if target_lang == "fr":
        return f"{translated_keyword} {number} : "  # French uses space before colon
    else:
        return f"{translated_keyword} {number}: "


def validate_section_numbers(source: str, translation: str, section_prefix: str, target_lang: str) -> str:
    """Validate section numbers are preserved in translation. Auto-fix if missing.
    
    Args:
        source: Original source text (without prefix - just content)
        translation: Translated text (should have prefix)
        section_prefix: Original section prefix (e.g., "Section 1: ")
        target_lang: Target language code
        
    Returns:
        Fixed translation with section prefix if it was missing
    """
    if not section_prefix:
        return translation  # No section prefix to validate
    
    # Check if translation already has the prefix (in any language)
    pattern = r'^(Section|Chapter|Part|Chapitre|Partie)\s+\d+[.\)]?\s*:?\s*'
    if re.match(pattern, translation, re.IGNORECASE):
        # Translation already has a section prefix - good!
        return translation
    
    # Section prefix is missing - auto-fix by adding it
    logger.warning(f"Section prefix '{section_prefix}' missing from translation. Auto-fixing...")
    translated_prefix = translate_section_prefix(section_prefix, target_lang)
    return f"{translated_prefix}{translation}"


def emergency_translate(
    masked_block: MaskedBlock,
    backend: TranslationBackend,
    source_lang: str,
    target_lang: str,
    masker: MaskingEngine,
    temp: float = 0.9
) -> Optional[TranslatedBlock]:
    """Last-resort translation attempt with high temperature and simplified prompt.
    
    This is called when normal translation fails. Strategy:
    1. Use very high temperature (0.9) for creativity
    2. Simplified prompt (less rules to confuse model)
    3. Accept ANY result (even partial)
    4. If still fails, use source text (better than empty)
    
    Args:
        masked_block: The block to translate
        backend: Translation backend to use
        source_lang: Source language
        target_lang: Target language
        masker: Masking engine for placeholder restoration
        temp: Temperature (default 0.9 for maximum creativity)
        
    Returns:
        TranslatedBlock with best available result, or None if impossible
    """
    logger.info(f"🆘 Emergency translation for block {masked_block.block_id}")
    
    # Get original source text for fallback
    source_text = masked_block.masked_text
    
    # Simplified prompt - just translate, no complex rules
    simple_prompt = f"Translate this text from {source_lang} to {target_lang}. Preserve any placeholders like <<...>> or @@...@@."
    
    req = TranslateRequest(
        text=masked_block.masked_text,
        source_lang=source_lang,
        target_lang=target_lang,
        system_prompt=simple_prompt,
        temperature=temp,
        n_candidates=1,
        identity_threshold=0.99,  # Very permissive
        timeout=120.0,  # Give it time
    )
    
    try:
        result = backend.translate(req)
        if result.candidates and len(result.candidates) > 0:
            best = result.candidates[0]
            if best and best.strip():  # Accept ANY non-empty result
                # Try to restore placeholders (but accept even if restore fails)
                try:
                    restored, errors = masker.restore(best, masked_block.registry)
                    if restored and restored.strip():
                        logger.info(f"✅ Emergency translation succeeded for {masked_block.block_id}")
                        return TranslatedBlock(
                            block_id=masked_block.block_id,
                            source_text=source_text,
                            translated_text=restored,
                            ok=True,
                            errors=errors if errors else [],
                            meta={"emergency_translation": True, "temperature": temp},
                        )
                    else:
                        # Restoration failed but we have translation - use it anyway
                        logger.warning(f"⚠️ Emergency translation succeeded but placeholder restore failed for {masked_block.block_id}")
                        return TranslatedBlock(
                            block_id=masked_block.block_id,
                            source_text=source_text,
                            translated_text=best,  # Use translation even without placeholders
                            ok=True,
                            errors=["placeholder_restore_failed"] + (errors if errors else []),
                            meta={"emergency_translation": True, "temperature": temp, "placeholder_restore_failed": True},
                        )
                except Exception as restore_error:
                    # Restoration error - use translation anyway
                    logger.warning(f"⚠️ Emergency translation succeeded but restore error for {masked_block.block_id}: {restore_error}")
                    return TranslatedBlock(
                        block_id=masked_block.block_id,
                        source_text=source_text,
                        translated_text=best,
                        ok=True,
                        errors=["restore_error"],
                        meta={"emergency_translation": True, "temperature": temp, "restore_error": str(restore_error)},
                    )
    except Exception as e:
        logger.error(f"Emergency translation failed for {masked_block.block_id}: {e}")
    
    # Absolute last resort: use source text (better than empty)
    logger.warning(f"⚠️ Using source text for block {masked_block.block_id} (better than empty)")
    return TranslatedBlock(
        block_id=masked_block.block_id,
        source_text=source_text,
        translated_text=source_text,  # Use source as fallback
        ok=False,
        errors=["emergency_fallback_to_source"],
        meta={"used_source_text": True},
    )


def _translate_single_block(
    mb: MaskedBlock,
    idx: int,
    total: int,
    backend: TranslationBackend,
    cfg: PipelineConfig,
    doc: Document,
    masker: MaskingEngine,
    glossary: Optional[dict[str, str]],
    glossary_manager: Optional[GlossaryManager],
    pre_scores_by_id: dict[str, Any],
    cancel_event: Optional[threading.Event],
    cache: TranslationCache | None,
    translation_memory: TranslationMemory | None,
) -> tuple[TranslatedBlock, str]:
    """Translate a single block. Returns (TranslatedBlock, translated_text)."""
    if cancel_event is None:
        cancel_event = threading.Event()
    if cancel_event.is_set():
        raise RuntimeError("Translation cancelled by user")
    
    # Get source text
    source_text = ""
    for page in doc.pages:
        for block in page.blocks:
            if block.id == mb.block_id:
                source_text = _block_text(block)
                break
    
    # Enhanced logging for CLI visibility
    console.print(f"\n[cyan]📝 Block {idx+1}/{total}:[/cyan] {mb.block_id}")
    preview = source_text[:80] + "..." if len(source_text) > 80 else source_text
    console.print(f"   [dim]Source:[/dim] {preview}")
    
    logger.info(f"[{idx+1}/{total}] Translating block {mb.block_id}")
    pre_score = pre_scores_by_id.get(mb.block_id)
    
    # Adapt parameters based on complexity
    if pre_score and pre_score.is_complex():
        block_n_candidates = pre_score.recommended_candidates
        block_temperature = pre_score.recommended_temperature
        console.print(f"   [yellow]⚙️  Complex block detected:[/yellow] {block_n_candidates} candidates, temp={block_temperature:.1f}")
    else:
        block_n_candidates = cfg.n_candidates
        block_temperature = cfg.temperature
    
    # Get block metadata
    is_header_block = False
    is_bullet_block = False
    is_table_block = False
    block_meta: dict[str, Any] = {}
    for page in doc.pages:
        for block in page.blocks:
            if block.id == mb.block_id:
                block_meta = block.meta or {}
                is_header_block = block_meta.get("is_header", False)
                source_text_check = _block_text(block)
                is_bullet_block = any(
                    source_text_check.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"]
                )
                is_table_block = block_meta.get("block_type") == "table" or block_meta.get("is_table", False)
                break
    
    # CRITICAL: For headers, always generate multiple candidates and use reranking
    # This helps avoid wrong translations like "Section 1: Introduction" → "Document layout result"
    if is_header_block:
        block_n_candidates = max(block_n_candidates, 3)  # At least 3 candidates for headers
        console.print(f"   [magenta]📌 Header/Title block - generating {block_n_candidates} candidates for quality[/magenta]")
    
    # Log special block types
    if is_bullet_block:
        console.print(f"   [blue]• Bullet point[/blue]")
    
    # Build enhanced prompt with relevant glossary terms
    relevant_glossary = None
    if glossary and source_text:
        source_lower = source_text.lower()
        relevant_glossary = {
            k: v for k, v in glossary.items() if k and k.lower() in source_lower
        }
    enhanced_prompt = build_system_prompt(
        source=cfg.source_lang,
        target=cfg.target_lang,
        glossary=relevant_glossary,
        source_text=source_text,
        is_header=is_header_block,
        is_bullet=is_bullet_block,
        is_table=is_table_block,
    )
    prompt_version = get_prompt_version()
    
    # Create translation request with proper context
    req = TranslateRequest(
        text=mb.masked_text,
        source_lang=cfg.source_lang,
        target_lang=cfg.target_lang,
        system_prompt=enhanced_prompt,
        temperature=block_temperature,
        n_candidates=block_n_candidates,
        context={
            "is_header": is_header_block,
            "block_id": mb.block_id,
            "block_type": block_meta.get("block_type", "paragraph"),
        },
    )
    
    # Translate (with cache + retries)
    console.print(f"   [cyan]🔄 Translating...[/cyan]")
    candidates: list[str] = []
    res_meta: dict = {}
    try:
        if cancel_event.is_set():
            raise RuntimeError("Translation cancelled by user")
        cache_version = _compute_cache_version(
            backend=backend,
            cfg=cfg,
            system_prompt=enhanced_prompt,
        )
        cache_key = None
        cached = None
        cache_status = "no_cache"
        if cache:
            cache_key = make_cache_key(
                backend.name,
                getattr(backend, "model", cfg.model),
                mb.masked_text,
                cfg.source_lang,
                cfg.target_lang,
                prompt_version=cache_version,
            )
            cached, cache_status = cache.get_with_status(
                cache_key,
                max_age_seconds=cfg.cache_ttl_seconds,
                expected_version=cache_version,
            )
            logger.debug(f"Block {mb.block_id}: Cache status={cache_status}")
        if cached and cached.get("candidates"):
            candidates = cached["candidates"]
            res_meta = {
                "backend": backend.name,
                "model": getattr(backend, "model", cfg.model),
                "cached": True,
                "cache_key": cache_key,
                "cache_version": cache_version,
                "cache_status": cache_status,
                "prompt_version": prompt_version,
                **(cached.get("meta") or {}),
            }
        else:
            memory_used = False
            if translation_memory and cfg.memory_use_fuzzy:
                memory_match = translation_memory.get_best_match(
                    mb.masked_text,
                    cfg.source_lang,
                    cfg.target_lang,
                    min_similarity=cfg.memory_min_similarity,
                    max_age_seconds=cfg.memory_ttl_seconds,
                )
                if memory_match:
                    mem_text, mem_score, mem_meta = memory_match
                    if not mb.registry or all(ph in mem_text for ph in mb.registry.keys()):
                        candidates = [mem_text]
                        res_meta = {
                            "backend": backend.name,
                            "model": getattr(backend, "model", cfg.model),
                            "cached": False,
                            "memory_hit": True,
                            "memory_score": mem_score,
                            "prompt_version": prompt_version,
                            **(mem_meta or {}),
                        }
                        memory_used = True
            if memory_used:
                logger.info(f"Block {mb.block_id}: Using translation memory match")
            else:
                max_retries = max(0, cfg.max_translation_retries)
                attempt = 0
                last_error: Exception | None = None
                while attempt <= max_retries:
                    try:
                        res = backend.translate(req)
                        candidates = res.candidates if res.candidates else [""]
                        res_meta = {
                            "backend": backend.name,
                            "model": getattr(backend, "model", cfg.model),
                            "cached": False,
                            "prompt_version": prompt_version,
                            **res.meta,
                        }
                        break
                    except Exception as e:
                        last_error = e
                        if attempt >= max_retries:
                            raise
                        jitter = random.uniform(0.05, 0.3) * (2**attempt)
                        logger.warning(
                            f"Block {mb.block_id}: Translation retry {attempt+1}/{max_retries} after error: {e}"
                        )
                        time.sleep(jitter)
                        attempt += 1
                if cache and cache_key and candidates:
                    cache.set(
                        cache_key,
                        candidates,
                        res_meta,
                        version=cache_version,
                    )
        # Log candidates
        if len(candidates) > 1:
            console.print(f"   [green]✓ Got {len(candidates)} candidates[/green]")
            for i, cand in enumerate(candidates[:3], 1):  # Show max 3
                cand_preview = cand[:60] + "..." if len(cand) > 60 else cand
                console.print(f"      [{i}] {cand_preview}")
        else:
            cand_preview = candidates[0][:60] + "..." if len(candidates[0]) > 60 else candidates[0]
            console.print(f"   [green]✓ Translation:[/green] {cand_preview}")
            logger.info(
                f"Block {mb.block_id}: Translation received\n"
                f"  Translation ({len(candidates[0])} chars): '{candidates[0][:100]}...'\n"
                f"  Backend: {backend.name}"
            )
    except Exception as e:
        logger.error(f"Block {mb.block_id}: Backend translation failed: {e}", exc_info=True)
        console.print(f"   [red]❌ Translation failed: {e}[/red]")
        candidates = [""]
        res_meta = {"backend": backend.name, "model": getattr(backend, "model", cfg.model), "cached": False, "error": str(e)}
    
    # Rerank if enabled
    if cfg.enable_reranking and len(candidates) > 1:
        console.print(f"   [yellow]⚖️  Reranking candidates...[/yellow]")
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
            glossary=relevant_glossary,
            is_header=is_header_for_rerank,
        )
        if ranked:
            candidates = [c for c, _ in ranked]
            res_meta["rerank_scores"] = {"best_score": ranked[0][1].total, "best_valid": ranked[0][1].is_valid()}
            # Show top 3 ranked
            console.print(f"   [green]📊 Reranked results:[/green]")
            for i, (cand, score) in enumerate(ranked[:3], 1):
                cand_preview = cand[:50] + "..." if len(cand) > 50 else cand
                console.print(f"      [{i}] Score={score.total:.2f} {cand_preview}")
    
    # Restore placeholders
    candidate = candidates[0] if candidates else ""
    
    # CRITICAL: Check for FAKE placeholders (generated by LLM, not in registry)
    fake_placeholder_detected = False
    if candidate and mb.registry:
        # Find all placeholders in candidate
        import re
        candidate_placeholders = set(re.findall(r'@@SCITRANS_[A-Z0-9_]+_\d{4}_[A-F0-9]{8}@@', candidate))
        candidate_placeholders |= set(re.findall(r'<<[^<>]+>>', candidate))
        candidate_placeholders |= set(re.findall(r'⟦[^⟦⟧]+⟧', candidate))
        # Find all placeholders in registry
        registry_placeholders = set(mb.registry.keys())
        # Check if candidate has placeholders NOT in registry
        fake_placeholders = candidate_placeholders - registry_placeholders
        if fake_placeholders:
            fake_placeholder_detected = True
            logger.error(f"Block {mb.block_id}: LLM GENERATED FAKE PLACEHOLDERS: {fake_placeholders}")
            logger.error(f"Block {mb.block_id}: These placeholders were NOT in source - this is hallucination!")
            # Remove fake placeholders before restoration
            for fake in fake_placeholders:
                candidate = candidate.replace(fake, "")
                logger.warning(f"Block {mb.block_id}: Removed fake placeholder {fake}")
    
    restored, restore_errors = masker.restore(candidate, mb.registry, tolerant=True)
    missing_placeholders = [e for e in restore_errors if e.startswith("missing_placeholder:")]
    if missing_placeholders and candidate.strip() and mb.registry:
        logger.warning(
            f"Block {mb.block_id}: Missing placeholders after restore ({len(missing_placeholders)}). "
            "Attempting one-shot placeholder repair."
        )
        repair_prompt = (
            f"{enhanced_prompt}\n\n"
            "STRICT PLACEHOLDER RULES:\n"
            "- Preserve all @@SCITRANS_...@@ tokens EXACTLY as-is.\n"
            "- Do NOT translate or alter the placeholder tokens.\n"
            "- Do NOT delete placeholders.\n"
            "- Output the full translation with the same placeholders included."
        )
        try:
            repair_req = TranslateRequest(
                text=mb.masked_text,
                source_lang=cfg.source_lang,
                target_lang=cfg.target_lang,
                system_prompt=repair_prompt,
                temperature=min(block_temperature, 0.2),
                n_candidates=1,
                context=context_text,
            )
            repair_res = backend.translate(repair_req)
            if repair_res and repair_res.candidates and repair_res.candidates[0].strip():
                repaired_candidate = repair_res.candidates[0]
                restored, restore_errors = masker.restore(repaired_candidate, mb.registry, tolerant=True)
                missing_placeholders = [e for e in restore_errors if e.startswith("missing_placeholder:")]
                if missing_placeholders:
                    logger.error(
                        f"Block {mb.block_id}: Placeholder repair failed; falling back to source text."
                    )
                    restored = source_text
                    restore_errors = ["placeholder_restore_failed"] + restore_errors
        except Exception as repair_error:
            logger.error(
                f"Block {mb.block_id}: Placeholder repair failed with error: {repair_error}"
            )
            restored = source_text
            restore_errors = ["placeholder_restore_failed"]
    if glossary_manager and restored:
        restored, glossary_stats = glossary_manager.enforce_translation(source_text, restored)
        if glossary_stats.terms_violated:
            logger.warning(
                f"Block {mb.block_id}: Glossary violations={glossary_stats.terms_violated} "
                f"adherence={glossary_stats.adherence_rate:.2f}"
            )
    
    # PHASE 2.1 & 2.3: Handle section prefix extraction and validation
    section_prefix = mb.meta.get("section_prefix", "") if mb.meta else ""
    content_only_text = mb.meta.get("content_only", source_text) if mb.meta else source_text
    
    if section_prefix:
        # PHASE 2.3: Validate that translation has section prefix
        # If not, add it (auto-fix)
        # Pass content_only_text (not source_text) to avoid double prefix
        restored = validate_section_numbers(content_only_text, restored, section_prefix, cfg.target_lang)
        logger.info(f"Block {mb.block_id}: Validated section prefix in translation")
    
    # CRITICAL: Hallucination detection - check if translation is WAY longer than source
    hallucination_detected = False
    if restored.strip() and source_text.strip():
        # For comparison, use original full text (WITH prefix if it exists)
        comparison_source = mb.meta.get("original_full_text", source_text) if mb.meta else source_text
        source_len = len(comparison_source.strip())
        restored_len = len(restored.strip())
        length_ratio = restored_len / source_len if source_len > 0 else 0
        
        # PHASE 2.4: Stricter hallucination detection for headers
        if is_header_block:
            max_ratio = 2.0  # Headers can be at most 2x source length
        else:
            # For very short blocks (<50 chars), allow max 3x expansion
            # For longer blocks, allow max 2x expansion
            max_ratio = 3.0 if source_len < 50 else 2.0
        
        if length_ratio > max_ratio:
            hallucination_detected = True
            logger.error(f"Block {mb.block_id}: HALLUCINATION - Translation {length_ratio:.1f}x longer than source!")
            logger.error(f"Block {mb.block_id}: Source ({source_len} chars): '{comparison_source[:100]}'")
            logger.error(f"Block {mb.block_id}: Translation ({restored_len} chars): '{restored[:100]}'")
    
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
    
    placeholders_ok = (
        not candidate_empty
        and (len(registry) == 0 or masker.placeholders_present(candidate, registry))
    )

    ok = (
        placeholders_ok 
        and len(restore_errors) == 0 
        and not identity_translation 
        and not wrong_translation 
        and not hallucination_detected 
        and not fake_placeholder_detected
        and restored.strip() != ""
    )
    
    # Collect errors
    errors = []
    if restore_errors:
        errors.extend(restore_errors)
    if hallucination_detected:
        errors.append("hallucination")
    if fake_placeholder_detected:
        errors.append("fake_placeholders")
    if identity_translation:
        errors.append("identity_translation")
        # Enhanced logging for identity translations
        from difflib import SequenceMatcher
        similarity = SequenceMatcher(None, source_text, restored).ratio() if restored else 0.0
        logger.warning(
            f"Block {mb.block_id}: Identity translation detected\n"
            f"  Source: '{source_text[:100]}'\n"
            f"  Translation: '{restored[:100] if restored else 'EMPTY'}'\n"
            f"  Similarity: {similarity:.2%}\n"
            f"  Is Header: {is_header_block}\n"
            f"  Action: {'Will retry with emergency translation' if identity_result.should_retry else 'Accepting (may be valid for technical terms)'}"
        )
    if wrong_translation:
        errors.append("wrong_translation")
    if not errors and not ok:
        errors.append("validation_failed")
    
    # Create TranslatedBlock
    tb = TranslatedBlock(
        block_id=mb.block_id,
        source_text=mb.masked_text,
        translated_text=restored if ok or not hallucination_detected else source_text,  # Use source if hallucination
        ok=ok,
        errors=errors,
        meta=res_meta,
    )
    
    # Enhanced logging for block completion
    status = "✅ SUCCESS" if ok else "❌ FAILED"
    logger.info(
        f"Block {mb.block_id}: Translation complete - {status}\n"
        f"  Source: '{mb.masked_text[:100]}...'\n"
        f"  Translation: '{restored[:100] if restored else 'EMPTY'}...'\n"
        f"  Errors: {errors if errors else 'None'}\n"
        f"  Final status: {'OK' if ok else 'FAILED'}"
    )

    if translation_memory and ok and restored and restored.strip():
        quality_score = None
        rerank_meta = res_meta.get("rerank_scores", {})
        if isinstance(rerank_meta, dict):
            quality_score = rerank_meta.get("best_score")
        translation_memory.add(
            source=mb.masked_text,
            target=restored,
            source_lang=cfg.source_lang,
            target_lang=cfg.target_lang,
            metadata={
                "backend": backend.name,
                "model": getattr(backend, "model", cfg.model),
                "quality_score": quality_score or 0.0,
                "prompt_version": res_meta.get("prompt_version"),
            },
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
    out_dir = Path(cfg.output_dir) / Path(input_pdf).stem
    
    # CRITICAL: Clear all previous artifacts and cache for this PDF to ensure fresh translation
    if out_dir.exists():
        import shutil
        logger.info(f"Clearing previous artifacts: {out_dir}")
        try:
            shutil.rmtree(out_dir)
            logger.info(f"✓ Cleared cache/artifacts for fresh translation")
        except Exception as e:
            logger.warning(f"Could not clear artifacts: {e}")
    
    # Ensure output directory exists
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if False:  # Placeholder to maintain structure
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
            is_table_region = (
                block.meta.get("region") == "table"
                or block.meta.get("block_type") == "table"
                or block.meta.get("is_table", False)
                or is_table_candidate(block)
            )
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
            
            if detected_lang not in (cfg.source_lang, cfg.target_lang) and lang_confidence > 0.5:
                # Block is in a different language - preserve it
                skipped_blocks.append((block.id, f"preserve_lang_{detected_lang}"))
                logger.info(
                    f"Preserving block {block.id} in language {detected_lang} "
                    f"(confidence: {lang_confidence:.2f}) - not translating"
                )
                # Store original text as translation to preserve it
                translations[block.id] = src
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
            
            # PHASE 2.1: Extract section prefix for headers (pre-processing)
            section_prefix = ""
            content_only = src  # Content without prefix
            if block.meta.get("is_header"):
                section_prefix, content_only = extract_section_prefix(src)
                if section_prefix:
                    logger.info(f"Extracted section prefix '{section_prefix}' from block {block.id}, content: '{content_only}'")
            
            # Pass CONTENT ONLY to masker (without section prefix)
            masked, registry, counts = masker.mask(content_only, block=block)
            
            # PHASE 2.1: Create masked block with section prefix AND original full text in metadata
            meta_dict = {}
            if section_prefix:
                meta_dict["section_prefix"] = section_prefix
                meta_dict["original_full_text"] = src  # Store original WITH prefix
                meta_dict["content_only"] = content_only  # Store content WITHOUT prefix
            
            masked_block = MaskedBlock(
                block_id=block.id, 
                masked_text=masked, 
                registry=registry, 
                mask_counts=counts,
                meta=meta_dict
            )
            
            masked_blocks.append(masked_block)
    
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
    glossary_manager: GlossaryManager | None = None
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
            glossary_manager = glossary_mgr
            console.print(f"[green]✓ Total glossary terms: {len(glossary)}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Could not load domain glossaries: {e}[/yellow]")
    elif glossary and GlossaryManager:
        try:
            glossary_mgr = GlossaryManager()
            glossary_mgr.add_custom_terms(glossary)
            glossary = glossary_mgr.get_glossary_dict()
            glossary_manager = glossary_mgr
        except Exception as e:
            console.print(f"[yellow]⚠ Could not load custom glossary: {e}[/yellow]")

    # 3) Translate - cache/memory with TTL (if enabled)
    system_prompt = build_system_prompt(
        source=cfg.source_lang, target=cfg.target_lang, glossary=glossary
    )
    cache = TranslationCache(cache_dir=out_dir / ".cache") if cfg.use_cache else None
    translation_memory = TranslationMemory(cfg.memory_file) if cfg.use_memory else None
    if cache:
        logger.info(f"Cache enabled with TTL={cfg.cache_ttl_seconds}s")
    else:
        logger.info("Cache disabled - translating all blocks fresh")
    if translation_memory:
        logger.info(
            f"Translation memory enabled (file={cfg.memory_file}, ttl={cfg.memory_ttl_seconds}s)"
        )

    translated_blocks: list[TranslatedBlock] = []
    translations: dict[str, str] = {}
    # NO CONTEXT BUFFER - user doesn't care about context retention
    pre_scores_by_id = {s.block_id: s for s in pre_scores}

    # Initialize cancel event if not provided
    if cancel_event is None:
        cancel_event = threading.Event()

    # CONTENT TYPE DETECTION: Detect if document is academic/technical
    # This adjusts identity detection thresholds to allow technical terms
    from scitrans.utils.content_detector import detect_content_type, ContentType
    
    content_analysis = detect_content_type(doc)
    logger.info(f"Content analysis: {content_analysis.reasoning}")
    
    # Set identity thresholds based on content type
    if content_analysis.content_type == ContentType.ACADEMIC:
        identity_threshold_nonheader = 0.95  # Relaxed for academic (was 0.90)
        identity_threshold_header = 0.98     # Relaxed for academic headers (was 0.95)
        console.print(f"[cyan]📚 Academic content detected - using relaxed identity threshold (95/98%)[/cyan]")
        logger.info(
            f"Academic content detected: {content_analysis.technical_keyword_count} keywords, "
            f"{content_analysis.citation_count} citations, {content_analysis.math_density*100:.1f}% math"
        )
    else:
        identity_threshold_nonheader = 0.90  # Standard for general content
        identity_threshold_header = 0.95     # Standard for general headers
        logger.info(f"General content - using standard identity threshold (90/95%)")

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
    # PROGRESSIVE BATCHING: Helper function to create progressively larger batches
    def create_progressive_batches(
        blocks: list,
        start_size: int = 32,
        mid_size: int = 64,
        final_size: int = 96,
    ) -> list[list]:
        """Create progressively larger batches for translation.
        
        Strategy:
        - Blocks 0-200: 32 blocks/batch (conservative start)
        - Blocks 201-500: 64 blocks/batch (if stable)
        - Blocks 501+: 96 blocks/batch (maximum efficiency)
        
        This prevents overwhelming backends with huge batches while
        maintaining good performance for large documents.
        
        Args:
            blocks: List of blocks to batch
            start_size: Initial batch size (32)
            mid_size: Mid batch size for blocks 201-500 (64)
            final_size: Final batch size for blocks 501+ (96)
            
        Returns:
            List of batches (each batch is list of blocks)
        """
        if len(blocks) < start_size:
            # Small document: single batch
            return [blocks]
        
        batches = []
        idx = 0
        
        # Phase 1: Blocks 0-200 with start_size (32)
        while idx < min(200, len(blocks)):
            end_idx = min(idx + start_size, len(blocks))
            batches.append(blocks[idx:end_idx])
            idx = end_idx
        
        # Phase 2: Blocks 201-500 with mid_size (64)
        while idx < min(500, len(blocks)):
            end_idx = min(idx + mid_size, len(blocks))
            batches.append(blocks[idx:end_idx])
            idx = end_idx
        
        # Phase 3: Blocks 501+ with final_size (96)
        while idx < len(blocks):
            end_idx = min(idx + final_size, len(blocks))
            batches.append(blocks[idx:end_idx])
            idx = end_idx
        
        return batches
    
    # BATCHING SUPPORT: Check if backend supports translate_batch() for performance
    # Progressive batching: 32 blocks minimum, scales up for large documents
    use_progressive_batching = hasattr(backend, 'translate_batch') and len(masked_blocks) >= 32
    use_simple_batching = hasattr(backend, 'translate_batch') and 8 <= len(masked_blocks) < 32
    batch_completed_successfully = False  # Track if batch completed without falling back
    
    if use_progressive_batching:
        logger.info(f"Backend supports batching: Using PROGRESSIVE batching for {len(masked_blocks)} blocks")
        console.print(f"[cyan]⚡ Using progressive batch translation mode ({len(masked_blocks)} blocks)[/cyan]")
        
        # Create progressive batches (32→64→96)
        batches = create_progressive_batches(masked_blocks)
        logger.info(f"Split {len(masked_blocks)} blocks into {len(batches)} progressive batches")
        
        # Track batch statistics
        successful_blocks = 0
        failed_blocks = 0
        identity_failures = 0
        timeout_failures = 0
        
        try:
            for batch_num, batch_blocks in enumerate(batches, 1):
                logger.info(f"Processing batch {batch_num}/{len(batches)}: {len(batch_blocks)} blocks")
                console.print(f"[cyan]📦 Batch {batch_num}/{len(batches)}: {len(batch_blocks)} blocks[/cyan]")
                
                # Build translation requests for this batch
                requests = []
                request_to_mb = {}
                
                for idx, mb in enumerate(batch_blocks):
                    # Get source text and block metadata
                    source_text = ""
                    is_header = False
                    block_type = "normal"
                    
                    for page in doc.pages:
                        for block in page.blocks:
                            if block.id == mb.block_id:
                                source_text = _block_text(block)
                                is_header = block.meta.get("is_header", False)
                                block_type = block.meta.get("block_type", "normal")
                                break
                    is_bullet = any(source_text.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"])
                    relevant_glossary = None
                    if glossary and source_text:
                        source_lower = source_text.lower()
                        relevant_glossary = {
                            k: v for k, v in glossary.items() if k and k.lower() in source_lower
                        }
                    
                    # Mask source text
                    masked, registry, counts = masker.mask(source_text, None)
                    
                    # Build system prompt
                    system_prompt = build_system_prompt(
                        source=cfg.source_lang,
                        target=cfg.target_lang,
                        glossary=relevant_glossary,
                        source_text=source_text,
                        is_header=is_header,
                        is_bullet=is_bullet,
                        is_table=block_type == "table",
                    )
                    
                    # Calculate per-request timeout based on text length
                    # Formula: 10s per 50 chars, minimum 60s
                    text_length = len(masked)
                    per_request_timeout = max(60.0, (text_length / 50) * 10)
                    
                    # Create request with identity threshold and timeout
                    req = TranslateRequest(
                        text=masked,
                        source_lang=cfg.source_lang,
                        target_lang=cfg.target_lang,
                        system_prompt=system_prompt,
                        temperature=cfg.temperature,
                        n_candidates=cfg.n_candidates,
                        context={"is_header": is_header, "block_type": block_type, "block_id": mb.block_id},
                        identity_threshold=identity_threshold_header if is_header else identity_threshold_nonheader,
                        is_header=is_header,
                        timeout=per_request_timeout,
                    )
                    requests.append(req)
                    request_to_mb[len(requests) - 1] = (mb, masked, registry, source_text)
                
                # Execute this batch
                batch_results = backend.translate_batch(requests)
                
                # Process results - accept partial results (better than nothing)
                for idx, result in enumerate(batch_results):
                    mb, masked, registry, source_text = request_to_mb[idx]
                    
                    # Extract best candidate
                    if result and result.candidates and result.candidates[0]:
                        best_translation = result.candidates[0]
                        
                        # NEW: Accept partial results if better than nothing
                        if best_translation and len(best_translation.strip()) > 0:
                            # Restore placeholders
                            try:
                                restored, errors = masker.restore(best_translation, registry)
                                
                                # Even if restore has errors, use it (better than nothing)
                                is_success = len(restored.strip()) > 0 if restored else False
                                
                                # Use restored if available, otherwise use original translation
                                final_text = restored if restored and restored.strip() else best_translation
                                
                                if is_success:
                                    successful_blocks += 1
                                else:
                                    failed_blocks += 1
                                    # Check error types for statistics
                                    if result.meta:
                                        error_str = str(result.meta.get("error", "")).lower()
                                        if "identity" in error_str:
                                            identity_failures += 1
                                        elif "timeout" in error_str:
                                            timeout_failures += 1
                                
                                tb = TranslatedBlock(
                                    block_id=mb.block_id,
                                    source_text=source_text,
                                    translated_text=final_text,
                                    ok=is_success,
                                    errors=errors if errors else [],
                                    meta={**(result.meta or {}), "partial_result": not is_success},
                                )
                            except Exception as restore_error:
                                # Restoration error - use translation anyway (better than nothing)
                                logger.warning(f"Placeholder restore failed for {mb.block_id}, using translation anyway: {restore_error}")
                                failed_blocks += 1
                                tb = TranslatedBlock(
                                    block_id=mb.block_id,
                                    source_text=source_text,
                                    translated_text=best_translation,  # Use translation even without placeholders
                                    ok=False,
                                    errors=["restore_error"],
                                    meta={**(result.meta or {}), "restore_error": str(restore_error), "needs_emergency_retry": True},
                                )
                        else:
                            # Empty result - will be retried in emergency phase
                            failed_blocks += 1
                            tb = TranslatedBlock(
                                block_id=mb.block_id,
                                source_text=source_text,
                                translated_text="",
                                ok=False,
                                errors=["empty_translation"],
                                meta={"needs_emergency_retry": True},
                            )
                    else:
                        # No result - will be retried in emergency phase
                        failed_blocks += 1
                        tb = TranslatedBlock(
                            block_id=mb.block_id,
                            source_text=source_text,
                            translated_text="",
                            ok=False,
                            errors=["no_translation_result"],
                            meta={"needs_emergency_retry": True},
                        )
                    
                    translated_blocks.append(tb)
                
                # Log batch statistics with detailed information
                total_processed = successful_blocks + failed_blocks
                success_rate = successful_blocks / total_processed if total_processed > 0 else 0.0
                logger.info(
                    f"Batch {batch_num}/{len(batches)} complete:\n"
                    f"  Success: {successful_blocks}, Failed: {failed_blocks} (rate: {success_rate:.1%})\n"
                    f"  Identity failures: {identity_failures}, Timeout failures: {timeout_failures}\n"
                    f"  Total blocks in batch: {len(requests)}"
                )
                console.print(
                    f"[cyan]📊 Batch {batch_num}/{len(batches)}: "
                    f"✅ {successful_blocks} success, ❌ {failed_blocks} failed "
                    f"({success_rate:.1%} success rate)[/cyan]"
                )
                if identity_failures > 0 or timeout_failures > 0:
                    console.print(
                        f"[dim]  Identity failures: {identity_failures}, "
                        f"Timeout failures: {timeout_failures}[/dim]"
                    )
            
            logger.info(
                f"Progressive batch translation complete: {len(translated_blocks)} blocks translated\n"
                f"  Total blocks processed: {len(translated_blocks)}\n"
                f"  Successful: {sum(1 for tb in translated_blocks if tb.ok)}\n"
                f"  Failed: {sum(1 for tb in translated_blocks if not tb.ok)}"
            )
            successful_count = sum(1 for tb in translated_blocks if tb.ok)
            failed_count = sum(1 for tb in translated_blocks if not tb.ok)
            console.print(
                f"[green]✅ Progressive batch complete: {len(translated_blocks)} blocks "
                f"({successful_count} success, {failed_count} failed)[/green]"
            )
            batch_completed_successfully = True
            
            # EMERGENCY RETRY: Retry any failed blocks with emergency translation
            failed_block_indices = []
            for idx, tb in enumerate(translated_blocks):
                if not tb.ok or not tb.translated_text or tb.translated_text.strip() == "":
                    failed_block_indices.append(idx)
            
            if failed_block_indices:
                logger.warning(f"🚨 {len(failed_block_indices)} blocks failed - attempting emergency retry...")
                console.print(f"[yellow]🆘 Emergency retry for {len(failed_block_indices)} failed blocks...[/yellow]")
                
                for idx in failed_block_indices:
                    # Find corresponding masked block
                    mb = None
                    for page in doc.pages:
                        for block in page.blocks:
                            if block.id == translated_blocks[idx].block_id:
                                # Re-mask the source text
                                source_text = _block_text(block)
                                masked, registry, _ = masker.mask(source_text, None)
                                mb = MaskedBlock(
                                    block_id=block.id,
                                    masked_text=masked,
                                    registry=registry,
                                )
                                break
                        if mb:
                            break
                    
                    if mb:
                        emergency_result = emergency_translate(
                            mb, backend, cfg.source_lang, cfg.target_lang, masker, temp=0.9
                        )
                        if emergency_result:
                            translated_blocks[idx] = emergency_result
                            logger.info(f"✅ Emergency retry succeeded for block {mb.block_id}")
                        else:
                            logger.error(f"❌ Emergency retry failed for block {mb.block_id}")
                    else:
                        logger.error(f"❌ Could not find masked block for failed block {translated_blocks[idx].block_id}")
            
        except Exception as e:
            logger.error(f"Progressive batch translation failed: {e}", exc_info=True)
            console.print(f"[red]❌ Batch translation failed, falling back to sequential[/red]")
            batch_completed_successfully = False
    
    elif use_simple_batching:
        logger.info(f"Backend supports batching: Using simple batching for {len(masked_blocks)} blocks")
        console.print(f"[cyan]⚡ Using batch translation mode ({len(masked_blocks)} blocks)[/cyan]")
        
        # Build all translation requests
        requests = []
        request_to_mb = {}  # Map request index to masked block
        
        for idx, mb in enumerate(masked_blocks):
            # Get source text and block metadata
            source_text = ""
            is_header = False
            block_type = "normal"
            
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == mb.block_id:
                        source_text = _block_text(block)
                        is_header = block.meta.get("is_header", False)
                        block_type = block.meta.get("block_type", "normal")
                        break
            is_bullet = any(source_text.strip().startswith(bullet) for bullet in ["•", "-", "*", "·"])
            relevant_glossary = None
            if glossary and source_text:
                source_lower = source_text.lower()
                relevant_glossary = {
                    k: v for k, v in glossary.items() if k and k.lower() in source_lower
                }
            
            # Mask source text
            masked, registry, counts = masker.mask(source_text, None)
            
            # Build system prompt
            system_prompt = build_system_prompt(
                source=cfg.source_lang,
                target=cfg.target_lang,
                glossary=relevant_glossary,
                source_text=source_text,
                is_header=is_header,
                is_bullet=is_bullet,
                is_table=block_type == "table",
            )
            
            # Calculate per-request timeout based on text length
            # Formula: 10s per 50 chars, minimum 60s
            text_length = len(masked)
            per_request_timeout = max(60.0, (text_length / 50) * 10)
            
            # Create request with identity threshold and timeout
            req = TranslateRequest(
                text=masked,
                source_lang=cfg.source_lang,
                target_lang=cfg.target_lang,
                system_prompt=system_prompt,
                temperature=cfg.temperature,
                n_candidates=cfg.n_candidates,
                context={"is_header": is_header, "block_type": block_type, "block_id": mb.block_id},
                identity_threshold=identity_threshold_header if is_header else identity_threshold_nonheader,
                is_header=is_header,
                timeout=per_request_timeout,
            )
            requests.append(req)
            request_to_mb[len(requests) - 1] = (mb, masked, registry, source_text)
        
        # Execute batch translation
        logger.info(f"Submitting batch of {len(requests)} requests to backend")
        console.print(f"[cyan]📦 Translating {len(requests)} blocks in batch...[/cyan]")
        
        try:
            results = backend.translate_batch(requests)
            logger.info(f"Batch translation completed: {len(results)} results received")
            
            # PHASE 4: Validate no missing blocks
            if len(results) != len(requests):
                logger.error(
                    f"MISSING BLOCKS DETECTED: Sent {len(requests)} requests, "
                    f"got {len(results)} results! Missing: {len(requests) - len(results)} blocks"
                )
                # Pad results with None for missing blocks
                while len(results) < len(requests):
                    results.append(None)
                    logger.error(f"Added placeholder for missing block at index {len(results)-1}")
            
            # CRITICAL: Use the outer translated_blocks variable, don't create a new local one
            # Process results (append to existing translated_blocks from line 654) - accept partial results
            for idx, result in enumerate(results):
                mb, masked, registry, source_text = request_to_mb[idx]
                
                # Extract best candidate
                if result and result.candidates and result.candidates[0]:
                    best_translation = result.candidates[0]
                    
                    # NEW: Accept partial results if better than nothing
                    if best_translation and len(best_translation.strip()) > 0:
                        # Restore placeholders
                        try:
                            restored, errors = masker.restore(best_translation, registry)
                            
                            # Even if restore has errors, use it (better than nothing)
                            is_success = len(restored.strip()) > 0 if restored else False
                            
                            # Use restored if available, otherwise use original translation
                            final_text = restored if restored and restored.strip() else best_translation
                            
                            tb = TranslatedBlock(
                                block_id=mb.block_id,
                                source_text=source_text,
                                translated_text=final_text,
                                ok=is_success,
                                errors=errors if errors else [],
                                meta={**(result.meta or {}), "partial_result": not is_success},
                            )
                        except Exception as restore_error:
                            # Restoration error - use translation anyway (better than nothing)
                            logger.warning(f"Placeholder restore failed for {mb.block_id}, using translation anyway: {restore_error}")
                            tb = TranslatedBlock(
                                block_id=mb.block_id,
                                source_text=source_text,
                                translated_text=best_translation,  # Use translation even without placeholders
                                ok=False,
                                errors=["restore_error"],
                                meta={**(result.meta or {}), "restore_error": str(restore_error), "needs_emergency_retry": True},
                            )
                    else:
                        # Empty result - will be retried in emergency phase
                        tb = TranslatedBlock(
                            block_id=mb.block_id,
                            source_text=source_text,
                            translated_text="",
                            ok=False,
                            errors=["empty_translation"],
                            meta={"needs_emergency_retry": True},
                        )
                else:
                    # No result - will be retried in emergency phase
                    tb = TranslatedBlock(
                        block_id=mb.block_id,
                        source_text=source_text,
                        translated_text="",
                        ok=False,
                        errors=["no_translation_result"],
                        meta={"needs_emergency_retry": True},
                    )
                
                translated_blocks.append(tb)
                
                # Log progress
                if (idx + 1) % 5 == 0:
                    logger.info(f"Processed {idx + 1}/{len(results)} batch results")
                    console.print(f"[cyan]📊 Processed {idx + 1}/{len(results)} results[/cyan]")
            
            logger.info(f"Batch translation complete: {len(translated_blocks)} blocks translated")
            console.print(f"[green]✅ Batch translation complete: {len(translated_blocks)} blocks[/green]")
            batch_completed_successfully = True  # Mark batch as successful
            
            # EMERGENCY RETRY: Retry any failed blocks with emergency translation
            failed_block_indices = []
            for idx, tb in enumerate(translated_blocks):
                if not tb.ok or not tb.translated_text or tb.translated_text.strip() == "":
                    failed_block_indices.append(idx)
            
            if failed_block_indices:
                logger.warning(f"🚨 {len(failed_block_indices)} blocks failed - attempting emergency retry...")
                console.print(f"[yellow]🆘 Emergency retry for {len(failed_block_indices)} failed blocks...[/yellow]")
                
                for idx in failed_block_indices:
                    # Find corresponding masked block
                    mb = None
                    for page in doc.pages:
                        for block in page.blocks:
                            if block.id == translated_blocks[idx].block_id:
                                # Re-mask the source text
                                source_text = _block_text(block)
                                masked, registry, _ = masker.mask(source_text, None)
                                mb = MaskedBlock(
                                    block_id=block.id,
                                    masked_text=masked,
                                    registry=registry,
                                )
                                break
                        if mb:
                            break
                    
                    if mb:
                        emergency_result = emergency_translate(
                            mb, backend, cfg.source_lang, cfg.target_lang, masker, temp=0.9
                        )
                        if emergency_result:
                            translated_blocks[idx] = emergency_result
                            logger.info(f"✅ Emergency retry succeeded for block {mb.block_id}")
                        else:
                            logger.error(f"❌ Emergency retry failed for block {mb.block_id}")
                    else:
                        logger.error(f"❌ Could not find masked block for failed block {translated_blocks[idx].block_id}")
            
        except Exception as e:
            logger.error(f"Batch translation failed: {e}", exc_info=True)
            console.print(f"[red]❌ Batch translation failed, falling back to sequential[/red]")
            batch_completed_successfully = False  # Batch failed, will use sequential
    
    # CRITICAL FIX: Only run sequential/parallel if batch didn't complete successfully
    # This prevents duplicate translations (batch + sequential both running)
    if batch_completed_successfully:
        # Batch completed - skip sequential/parallel paths entirely
        logger.info(f"✅ Batch completed successfully, skipping sequential/parallel translation")
        console.print(f"[green]✅ Batch complete - skipping fallback paths[/green]")
    else:
        # Batch didn't complete (wasn't used or failed) - use sequential/parallel fallback
        logger.info(f"🔄 Using sequential/parallel translation (batch_completed={batch_completed_successfully})")
        console.print(f"[yellow]🔄 Using sequential translation (batch was not used or failed)[/yellow]")
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
            translated_blocks_dict: dict[str, TranslatedBlock] = {}
            translations_dict: dict[str, str] = {}
            completed = 0
            
            def translate_block_parallel(mb: MaskedBlock, idx: int) -> tuple[str, TranslatedBlock, str]:
                """Translate a block in parallel with retries for stability."""
                if cancel_event.is_set():
                    raise RuntimeError("Translation cancelled")
                max_retries = max(0, cfg.max_translation_retries)
                attempt = 0
                while attempt <= max_retries:
                    try:
                        tb, restored = _translate_single_block(
                            mb,
                            idx,
                            len(masked_blocks),
                            backend,
                            cfg,
                            doc,
                            masker,
                            glossary,
                            glossary_manager,
                            pre_scores_by_id,
                            cancel_event,
                            cache,
                            translation_memory,
                        )
                        if tb.ok or attempt >= max_retries:
                            return mb.block_id, tb, restored
                    except RuntimeError:
                        raise  # Re-raise cancellation
                    except Exception as e:
                        if attempt >= max_retries:
                            logger.error(
                                f"Block {mb.block_id}: Parallel translation failed after retries: {e}",
                                exc_info=True,
                            )
                            tb = TranslatedBlock(
                                block_id=mb.block_id,
                                source_text=mb.masked_text,
                                translated_text="",
                                ok=False,
                                errors=[f"parallel_error: {e}"],
                                meta={},
                            )
                            return mb.block_id, tb, ""
                        jitter = random.uniform(0.05, 0.3) * (2**attempt)
                        logger.warning(
                            f"Block {mb.block_id}: Parallel retry {attempt+1}/{max_retries} after error: {e}"
                        )
                        time.sleep(jitter)
                    attempt += 1
                return mb.block_id, TranslatedBlock(
                    block_id=mb.block_id,
                    source_text=mb.masked_text,
                    translated_text="",
                    ok=False,
                    errors=["parallel_error: unknown"],
                    meta={},
                ), ""
            
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
            
            # Convert dicts to lists in deterministic order
            translated_blocks = []
            translations = {}
            for mb in masked_blocks:
                tb = translated_blocks_dict.get(mb.block_id)
                if not tb:
                    tb = TranslatedBlock(
                        block_id=mb.block_id,
                        source_text=mb.masked_text,
                        translated_text="",
                        ok=False,
                        errors=["parallel_missing_result"],
                        meta={},
                    )
                translated_blocks.append(tb)
                translations[mb.block_id] = translations_dict.get(mb.block_id, "")
            logger.info(f"Parallel translation complete: {completed}/{len(masked_blocks)} blocks")
        else:
            # Sequential translation (original logic with retry)
            for idx, mb in enumerate(masked_blocks):
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
                
                # CRITICAL FIX: Call _translate_single_block and append the result
                try:
                    tb, restored = _translate_single_block(
                        mb,
                        idx,
                        len(masked_blocks),
                        backend,
                        cfg,
                        doc,
                        masker,
                        glossary,
                        glossary_manager,
                        pre_scores_by_id,
                        cancel_event,
                        cache,
                        translation_memory,
                    )
                    translated_blocks.append(tb)
                    logger.debug(f"Block {mb.block_id}: Appended to translated_blocks (ok={tb.ok})")
                except Exception as e:
                    logger.error(f"Block {mb.block_id}: Translation failed: {e}", exc_info=True)
                    # Create a failed block so we don't lose track
                    tb = TranslatedBlock(
                        block_id=mb.block_id,
                        source_text=mb.masked_text,
                        translated_text="",
                        ok=False,
                        errors=[f"translation_error: {str(e)}"],
                        meta={"backend": backend.name, "error": str(e)}
                    )
                    translated_blocks.append(tb)
                
                # Skip the old inline translation code below
                continue
            
            # OLD CODE BELOW - will be removed after verification
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
            else:
                # Normal block: use config settings, but ensure at least 2 candidates if reranking is enabled
                block_n_candidates = max(cfg.n_candidates, 2 if cfg.enable_reranking else 1)
            block_temperature = cfg.temperature

            cache_key = None
            cached_result = None
            memory_match = None

            candidates: list[str] = []
            res_meta: dict = {}

            # Build enhanced prompt for headers/bullets
            # Build enhanced prompt for headers/bullets
            relevant_glossary = None
            if glossary and source_text_check:
                source_lower = source_text_check.lower()
                relevant_glossary = {
                    k: v for k, v in glossary.items() if k and k.lower() in source_lower
                }
            enhanced_prompt = build_system_prompt(
                source=cfg.source_lang,
                target=cfg.target_lang,
                glossary=relevant_glossary,
                source_text=source_text_check,
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
                            cleaned_context_block, _ = clean_instruction_spillover(prev_block.translated_text.strip())
                            if cleaned_context_block and cleaned_context_block.strip():
                                context_blocks.append(cleaned_context_block)
                
                if context_blocks:
                    context_text = "\n\n".join(context_blocks)
                    logger.debug(f"Block {mb.block_id}: Using context from {len(context_blocks)} previous blocks")
                    console.print(f"[dim]  📚 Using context from {len(context_blocks)} previous blocks[/dim]")
            
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
                res = None
                cache_version = _compute_cache_version(
                    backend=backend,
                    cfg=cfg,
                    system_prompt=enhanced_prompt,
                )
                if cache:
                    cache_key = make_cache_key(
                        backend.name,
                        getattr(backend, "model", cfg.model),
                        mb.masked_text,
                        cfg.source_lang,
                        cfg.target_lang,
                        prompt_version=cache_version,
                    )
                    cached_result = cache.get(
                        cache_key,
                        max_age_seconds=cfg.cache_ttl_seconds,
                        expected_version=cache_version,
                    )
                if cached_result and cached_result.get("candidates"):
                    candidates = cached_result["candidates"]
                    res_meta = {
                        "backend": backend.name,
                        "model": getattr(backend, "model", cfg.model),
                        "cached": True,
                        "cache_key": cache_key,
                        "cache_version": cache_version,
                        **(cached_result.get("meta") or {}),
                    }
                else:
                    res = backend.translate(req)
                    candidates = res.candidates if res.candidates else [""]
                    res_meta = {
                        "backend": backend.name,
                        "model": getattr(backend, "model", cfg.model),
                        "cached": False,
                        **res.meta,
                    }
                    if cache and cache_key:
                        cache.set(cache_key, candidates, res_meta, version=cache_version)
                
                # CRITICAL: Clean instruction spillover from backend responses
                from scitrans.utils.translation_cleaner import clean_instruction_spillover
                cleaned_candidates = []
                for cand in candidates:
                    if cand and cand.strip():
                        cleaned, _ = clean_instruction_spillover(cand)
                        if cleaned and cleaned.strip():
                            cleaned_candidates.append(cleaned)
                        else:
                            # If cleaning removed everything, keep original (might be a false positive)
                            cleaned_candidates.append(cand)
                    else:
                        cleaned_candidates.append(cand)
                
                candidates = cleaned_candidates

                if not res_meta:
                    res_meta = {
                        "backend": backend.name,
                        "model": getattr(backend, "model", cfg.model),
                        "cached": False,
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
                if backend.name == "cascade_free" and res and res.meta.get("backends_used"):
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
            for cand in candidates:
                if cand.strip():
                    # Normalize for comparison
                    source_norm = " ".join(source_text_for_rerank.strip().split()).lower()
                    cand_norm = " ".join(cand.strip().split()).lower()
                    # For headers/titles: completely reject identity translations
                    if is_header_for_rerank and source_norm == cand_norm:
                        filtered_out_identity.append(cand)
                        # Calculate similarity for detailed logging
                        from difflib import SequenceMatcher
                        similarity = SequenceMatcher(None, source_text_for_rerank, cand).ratio()
                        logger.warning(
                            f"Block {mb.block_id}: Filtering out identity translation candidate\n"
                            f"  Source: '{source_text_for_rerank[:100]}'\n"
                            f"  Translation: '{cand[:100]}'\n"
                            f"  Similarity: {similarity:.2%}\n"
                            f"  Is Header: {is_header_for_rerank}\n"
                            f"  Action: Filtering out (will retry with higher temperature)"
                        )
                        console.print(
                            f"[yellow]  ⚠ Filtered identity candidate (similarity: {similarity:.1%}): "
                            f"'{cand[:50]}...'[/yellow]"
                        )
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
                
    # EMERGENCY RETRY: Final pass - retry any remaining failed blocks
    failed_block_indices = []
    for idx, tb in enumerate(translated_blocks):
        if not tb.ok or not tb.translated_text or tb.translated_text.strip() == "":
            failed_block_indices.append(idx)
    
    if failed_block_indices:
        failed_block_ids = [translated_blocks[i].block_id for i in failed_block_indices]
        logger.warning(
            f"🚨 {len(failed_block_indices)} blocks still failed - attempting final emergency retry...\n"
            f"  Failed block IDs: {failed_block_ids[:5]}{'...' if len(failed_block_ids) > 5 else ''}\n"
            f"  Action: Final emergency retry with maximum temperature (0.9)"
        )
        console.print(
            f"[yellow]🆘 Final emergency retry for {len(failed_block_indices)} failed blocks...[/yellow]\n"
            f"[dim]  Block IDs: {', '.join(failed_block_ids[:3])}{'...' if len(failed_block_ids) > 3 else ''}[/dim]"
        )
        
        for idx in failed_block_indices:
            # Find corresponding masked block
            mb = None
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == translated_blocks[idx].block_id:
                        # Re-mask the source text
                        source_text = _block_text(block)
                        masked, registry, _ = masker.mask(source_text, None)
                        mb = MaskedBlock(
                            block_id=block.id,
                            masked_text=masked,
                            registry=registry,
                        )
                        break
                if mb:
                    break
            
            if mb:
                emergency_result = emergency_translate(
                    mb, backend, cfg.source_lang, cfg.target_lang, masker, temp=0.9
                )
                if emergency_result:
                    translated_blocks[idx] = emergency_result
                    logger.info(
                        f"✅ Final emergency retry succeeded for block {mb.block_id}\n"
                        f"  Translation length: {len(emergency_result.translated_text)} chars\n"
                        f"  Status: {'OK' if emergency_result.ok else 'Failed but has content'}"
                    )
                    console.print(f"[green]  ✅ Block {mb.block_id}: Final emergency retry succeeded[/green]")
                else:
                    logger.error(
                        f"❌ Final emergency retry failed for block {mb.block_id}\n"
                        f"  Action: Will use source text as fallback to ensure block appears in PDF"
                    )
                    console.print(f"[red]  ❌ Block {mb.block_id}: Final emergency retry failed[/red]")
            else:
                logger.error(
                    f"❌ Could not find masked block for failed block {translated_blocks[idx].block_id}\n"
                    f"  Action: Will use source text from TranslatedBlock as fallback"
                )
    
    num_ok = sum(1 for tb in translated_blocks if tb.ok)
    num_failed = sum(1 for tb in translated_blocks if not tb.ok)
    logger.info(f"Translation summary: {num_ok} OK, {num_failed} failed out of {len(translated_blocks)} blocks")
    console.print(f"[cyan]Translation complete: {num_ok}/{len(translated_blocks)} blocks OK, {num_failed} failed[/cyan]")
    
    # TRANSLATION QUALITY REPORT with comprehensive tracking
    total_blocks = len(translated_blocks)
    successful_blocks = sum(1 for tb in translated_blocks if tb.ok)
    failed_blocks_count = total_blocks - successful_blocks
    emergency_blocks = sum(1 for tb in translated_blocks if tb.meta.get("emergency_translation"))
    source_fallback_blocks = sum(1 for tb in translated_blocks if tb.meta.get("used_source_text"))
    partial_result_blocks = sum(1 for tb in translated_blocks if tb.meta.get("partial_result"))
    
    # Track error types for detailed reporting
    error_type_counts = {}
    failed_block_details = []
    for tb in translated_blocks:
        if not tb.ok:
            for error in tb.errors:
                error_type_counts[error] = error_type_counts.get(error, 0) + 1
            failed_block_details.append({
                "block_id": tb.block_id,
                "errors": tb.errors,
                "has_translation": bool(tb.translated_text and tb.translated_text.strip()),
            })
    
    logger.info("=" * 60)
    logger.info("TRANSLATION QUALITY REPORT")
    logger.info("=" * 60)
    logger.info(f"Total blocks: {total_blocks}")
    logger.info(f"Successful: {successful_blocks} ({successful_blocks/total_blocks*100:.1f}%)")
    logger.info(f"Failed: {failed_blocks_count} ({failed_blocks_count/total_blocks*100:.1f}%)")
    logger.info(f"Emergency translations: {emergency_blocks}")
    logger.info(f"Partial results (accepted): {partial_result_blocks}")
    logger.info(f"Source text fallbacks: {source_fallback_blocks}")
    if error_type_counts:
        error_summary = ", ".join(f"{k}: {v}" for k, v in sorted(error_type_counts.items(), key=lambda x: -x[1]))
        logger.info(f"Error breakdown: {error_summary}")
    if failed_block_details:
        logger.info(f"Failed blocks (first 5): {[d['block_id'] for d in failed_block_details[:5]]}")
    logger.info("=" * 60)
    
    if failed_blocks_count == 0:
        logger.info("🎉 PERFECT TRANSLATION - Zero failed blocks!")
        console.print("[green]🎉 PERFECT TRANSLATION - Zero failed blocks![/green]")
    elif source_fallback_blocks == 0:
        logger.info("✅ ALL BLOCKS TRANSLATED - No source text fallbacks needed!")
        console.print(f"[green]✅ ALL BLOCKS TRANSLATED - {emergency_blocks} emergency retries used[/green]")
    else:
        logger.warning(
            f"⚠️ {source_fallback_blocks} blocks used source text (review recommended)\n"
            f"  These blocks will appear in the output but may need manual translation"
        )
        console.print(
            f"[yellow]⚠️ {source_fallback_blocks} blocks used source text (review recommended)[/yellow]\n"
            f"[dim]  All blocks will still appear in the output PDF[/dim]"
        )
    
    # CRITICAL FIX: Store ALL translated blocks in translations dictionary
    # Store even failed/empty blocks to ensure no content is lost
    for tb in translated_blocks:
        if tb.translated_text and tb.translated_text.strip():
            translations[tb.block_id] = tb.translated_text
            logger.debug(f"Stored translation for {tb.block_id}: {len(tb.translated_text)} chars")
        else:
            # Store source text for failed/empty blocks to ensure they appear in PDF
            source_text = tb.source_text
            if not source_text or not source_text.strip():
                # Fallback: get from document
                for page in doc.pages:
                    for block in page.blocks:
                        if block.id == tb.block_id:
                            source_text = _block_text(block)
                            break
                    if source_text:
                        break
            translations[tb.block_id] = source_text if source_text else ""
            logger.warning(
                f"Block {tb.block_id}: Translation empty/failed, storing source text as fallback "
                f"({len(source_text) if source_text else 0} chars). Errors: {tb.errors}"
            )
    
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

    # PHASE 4: Verify all blocks were translated (no missing blocks)
    if len(translated_blocks) != len(masked_blocks):
        missing_count = len(masked_blocks) - len(translated_blocks)
        missing_block_ids = []
        translated_block_ids = {tb.block_id for tb in translated_blocks}
        for mb in masked_blocks:
            if mb.block_id not in translated_block_ids:
                missing_block_ids.append(mb.block_id)
        
        logger.error(
            f"MISSING BLOCKS DETECTED: {missing_count} blocks not translated! "
            f"Expected {len(masked_blocks)}, got {len(translated_blocks)}"
        )
        logger.error(f"Missing block IDs: {missing_block_ids[:10]}{'...' if len(missing_block_ids) > 10 else ''}")
        console.print(
            f"[red]❌ ERROR: {missing_count} blocks missing from translation! "
            f"This is a critical bug.[/red]"
        )
        console.print(f"[red]Missing block IDs: {', '.join(missing_block_ids[:5])}{'...' if len(missing_block_ids) > 5 else ''}[/red]")
    else:
        logger.info(f"✓ All {len(masked_blocks)} blocks accounted for in translation")
    
    # CRITICAL: Verify translations dict has entries for ALL document blocks
    all_block_ids = set()
    for page in doc.pages:
        for block in page.blocks:
            if block.type == "text":
                all_block_ids.add(block.id)
    
    missing_in_translations = []
    for block_id in all_block_ids:
        if block_id not in translations:
            missing_in_translations.append(block_id)
    
    if missing_in_translations:
        logger.error(
            f"CRITICAL: {len(missing_in_translations)} blocks missing from translations dict! "
            f"These blocks will not appear in the final PDF."
        )
        logger.error(f"Missing block IDs: {missing_in_translations[:10]}{'...' if len(missing_in_translations) > 10 else ''}")
        console.print(
            f"[red]❌ CRITICAL: {len(missing_in_translations)} blocks missing from translations dict![/red]"
        )
        # Add source text for missing blocks to prevent content loss
        for block_id in missing_in_translations:
            for page in doc.pages:
                for block in page.blocks:
                    if block.id == block_id:
                        source_text = _block_text(block)
                        translations[block_id] = source_text
                        logger.warning(f"Added source text fallback for missing block {block_id}")
                        break
                if block_id in translations:
                    break
    else:
        logger.info(f"✓ All {len(all_block_ids)} document blocks have entries in translations dict")
    
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
        
        # Calculate post-translation score (outside page loop to avoid duplicates)
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

    # Verify all blocks have translations
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
        missing_list = list(missing_blocks)[:10]
        logger.error(
            f"⚠️ {len(missing_blocks)} blocks have NO translation - using source text as fallback\n"
            f"  Missing block IDs: {missing_list}{'...' if len(missing_blocks) > 10 else ''}\n"
            f"  Action: Adding source text for all missing blocks to ensure they appear in PDF"
        )
        console.print(
            f"[red]⚠️ ERROR: {len(missing_blocks)} blocks missing translations - using source text[/red]\n"
            f"[dim]  Missing block IDs: {', '.join(missing_list[:3])}{'...' if len(missing_blocks) > 3 else ''}[/dim]"
        )
        # Add source text for missing blocks
        for block_id in missing_blocks:
            block_info = all_block_info.get(block_id)
            if block_info:
                source_text = _block_text(block_info["page"].blocks[0])  # Get from first block with this ID
                for page in doc.pages:
                    for block in page.blocks:
                        if block.id == block_id:
                            source_text = _block_text(block)
                            break
                    if source_text:
                        break
                translations[block_id] = source_text
                logger.warning(f"Added source text fallback for missing block {block_id} ({len(source_text)} chars)")
    
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
            if failed_headers:
                logger.warning(
                    f"⚠️ {len(failed_headers)} headers/titles are identity translations (not properly translated)\n"
                    f"  Failed header IDs: {failed_headers[:5]}{'...' if len(failed_headers) > 5 else ''}\n"
                    f"  Action: These will appear in output but may need manual review"
                )
                console.print(
                    f"[yellow]⚠️ WARNING: {len(failed_headers)} headers/titles are identity translations[/yellow]\n"
                    f"[dim]  These blocks will still appear in the output (using source text)[/dim]"
                )
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
            # source_numbering is a _DetectedNumbering dict-like object
            numbering_prefix = source_numbering.get('prefix', '') if isinstance(source_numbering, dict) else getattr(source_numbering, 'prefix', '')
            numbering_type = source_numbering.get('kind', '') if isinstance(source_numbering, dict) else getattr(source_numbering, 'kind', '')
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
        # Perfect renderer (100% font size preservation, exact positioning, bullet preservation)
        if cfg.render_mode == "perfect":
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
            # Consolidated to primary renderer for best style fidelity
            render_translated_pdf_perfect(
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
            # Consolidated to primary renderer for best style fidelity
            render_translated_pdf_perfect(
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
    source_text_for_prompt = ""
    if block_ids:
        for page in doc.pages:
            for block in page.blocks:
                if block.id == block_ids[0]:
                    source_text_for_prompt = _block_text(block)
                    break
            if source_text_for_prompt:
                break
    relevant_glossary = None
    if glossary and source_text_for_prompt:
        source_lower = source_text_for_prompt.lower()
        relevant_glossary = {
            k: v for k, v in glossary.items() if k and k.lower() in source_lower
        }
    system_prompt = build_system_prompt(
        source=cfg.source_lang,
        target=cfg.target_lang,
        glossary=relevant_glossary,
        source_text=source_text_for_prompt,
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
