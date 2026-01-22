"""Pre and post-translation scoring system.

This module implements comprehensive scoring at two stages:
1. Pre-scoring: Assess source text complexity before translation
2. Post-scoring: Evaluate translation quality after translation

Scores drive adaptive translation strategies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PreTranslationScore:
    """Pre-translation assessment of source block complexity.

    Used to adapt translation strategy (temperature, candidates, constraints).
    """

    block_id: str
    complexity_score: float  # 0.0-1.0 (higher = more complex)

    # Complexity factors
    has_math: bool
    has_code: bool
    has_urls: bool
    has_citations: bool
    has_tables: bool
    has_bullets: bool
    has_numbers: bool

    # Text characteristics
    sentence_count: int
    word_count: int
    avg_word_length: float
    technical_term_density: float  # Ratio of technical terms

    # Recommended strategy
    recommended_temperature: float  # Lower for complex text
    recommended_candidates: int  # More for complex text
    recommended_constraints: str  # "strict" | "normal" | "relaxed"

    def is_complex(self) -> bool:
        """Is this block complex enough to need special handling?"""
        return self.complexity_score > 0.6

    def needs_extra_candidates(self) -> bool:
        """Should we generate extra candidates for this block?"""
        return self.complexity_score > 0.7


@dataclass(frozen=True)
class PostTranslationScore:
    """Post-translation quality assessment.

    Comprehensive evaluation of translation quality.
    """

    block_id: str
    overall_score: float  # 0.0-1.0 (higher = better quality)

    # Quality dimensions
    placeholder_score: float  # Math/code preservation
    numeric_score: float  # Number accuracy
    format_score: float  # Bullets, structure
    fluency_score: float  # Language quality
    fidelity_score: float  # Meaning preservation

    # Specific issues
    issues: list[str]  # ["placeholder_missing", "numeric_drift", etc.]
    warnings: list[str]  # ["long_sentence", "unusual_structure", etc.]

    # Recommendations
    needs_review: bool
    needs_retry: bool
    confidence: float  # 0.0-1.0

    def is_acceptable(self) -> bool:
        """Is this translation acceptable without review?
        
        A block is acceptable only if:
        - Overall score is high enough
        - Doesn't need retry
        - Has no critical errors (identity_translation, validation_failed, etc.)
        """
        # Check for critical errors that make a block unacceptable
        critical_errors = [
            "identity_translation",
            "validation_failed",
            "wrong_translation_generic_response",
            "placeholder_missing",
            "placeholder_restoration_failed",  # Also critical
        ]
        has_critical_error = any(
            any(crit in err for crit in critical_errors) 
            for err in self.issues
        )
        
        return (
            self.overall_score >= 0.85 
            and not self.needs_retry 
            and not has_critical_error
        )


def compute_pre_translation_score(block_id: str, text: str) -> PreTranslationScore:
    """Assess source text complexity before translation.

    Used to adapt translation strategy based on content characteristics.
    """
    # Detect special content
    has_math = bool(re.search(r"\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]", text, re.DOTALL))
    has_code = bool(re.search(r"```|`[^`]+`", text))
    has_urls = bool(re.search(r"https?://|www\.", text))
    has_citations = bool(re.search(r"\[\d+\]|\[\d+,\s*\d+\]", text))
    has_tables = bool(re.search(r"\|.*\|", text))  # Markdown tables
    has_bullets = bool(re.search(r"^[\s]*[-•*]\s", text, re.MULTILINE))
    has_numbers = bool(re.search(r"\b\d+\.?\d*\b", text))

    # Text statistics
    sentences = re.split(r"[.!?]+", text)
    sentence_count = len([s for s in sentences if s.strip()])

    words = text.split()
    word_count = len(words)
    avg_word_length = sum(len(w) for w in words) / max(word_count, 1)

    # Technical term density (words > 8 chars, often technical)
    technical_words = [w for w in words if len(w) > 8]
    technical_term_density = len(technical_words) / max(word_count, 1)

    # Compute complexity score (0.0-1.0)
    complexity = 0.0

    # Special content adds complexity
    if has_math:
        complexity += 0.25
    if has_code:
        complexity += 0.20
    if has_tables:
        complexity += 0.15
    if has_urls or has_citations:
        complexity += 0.10
    if has_bullets:
        complexity += 0.05
    if has_numbers:
        complexity += 0.05

    # Text characteristics
    if avg_word_length > 6:
        complexity += 0.10
    if technical_term_density > 0.3:
        complexity += 0.10
    if sentence_count > 5:
        complexity += 0.05

    complexity = min(complexity, 1.0)

    # Recommend strategy based on complexity
    if complexity > 0.7:
        recommended_temp = 0.0
        recommended_candidates = 5
        recommended_constraints = "strict"
    elif complexity > 0.4:
        recommended_temp = 0.1
        recommended_candidates = 3
        recommended_constraints = "normal"
    else:
        recommended_temp = 0.2
        recommended_candidates = 3
        recommended_constraints = "relaxed"

    return PreTranslationScore(
        block_id=block_id,
        complexity_score=complexity,
        has_math=has_math,
        has_code=has_code,
        has_urls=has_urls,
        has_citations=has_citations,
        has_tables=has_tables,
        has_bullets=has_bullets,
        has_numbers=has_numbers,
        sentence_count=sentence_count,
        word_count=word_count,
        avg_word_length=avg_word_length,
        technical_term_density=technical_term_density,
        recommended_temperature=recommended_temp,
        recommended_candidates=recommended_candidates,
        recommended_constraints=recommended_constraints,
    )


def compute_post_translation_score(
    block_id: str,
    source_text: str,
    translated_text: str,
    registry: dict[str, str],
    errors: list[str],
    *,
    is_header: bool = False,
    is_title: bool = False,
    is_bullet: bool = False,
) -> PostTranslationScore:
    """Assess translation quality after translation.

    Comprehensive evaluation across multiple quality dimensions.
    """
    issues = list(errors)
    warnings = []
    
    # 0. Identity detection (critical for headers/titles)
    identity_score = 1.0
    if source_text.strip() and translated_text.strip():
        source_normalized = " ".join(source_text.strip().split()).lower()
        translated_normalized = " ".join(translated_text.strip().split()).lower()
        
        if source_normalized == translated_normalized:
            # Exact match = identity translation (bad)
            identity_score = 0.0
            if is_header or is_title:
                issues.append("identity_translation:header_exact_match")
            else:
                issues.append("identity_translation:exact_match")
        else:
            # Check similarity using character overlap
            source_chars = set(source_normalized)
            translated_chars = set(translated_normalized)
            if source_chars and translated_chars:
                overlap_ratio = len(source_chars & translated_chars) / len(source_chars | translated_chars)
                if overlap_ratio > 0.95:  # More than 95% character overlap
                    identity_score = 0.3
                    issues.append(f"identity_translation:high_similarity_{overlap_ratio:.2f}")
                elif overlap_ratio > 0.85:
                    identity_score = 0.6
                    warnings.append(f"identity_translation:moderate_similarity_{overlap_ratio:.2f}")

    # 1. Placeholder preservation (critical)
    # After restoration, placeholders should NOT be in translated_text (they've been replaced)
    # So successful restoration = placeholders NOT present in final text
    placeholder_score = 1.0
    if registry:
        # Check for restoration errors first (most reliable indicator of failure)
        has_restoration_error = any(
            "placeholder" in err.lower() 
            or "missing_placeholder" in err.lower()
            or "placeholder_restore" in err.lower()
            for err in errors
        )
        
        # Check if placeholders are still present in final text (shouldn't be after restoration)
        still_present = sum(1 for ph in registry if ph in translated_text)
        
        if has_restoration_error:
            # Restoration failed - calculate score based on what was restored
            if still_present > 0:
                # Some placeholders still present = partial restoration failure
                placeholder_score = (len(registry) - still_present) / len(registry)
            else:
                # No placeholders present but errors reported = restoration attempted but some failed
                # Count missing placeholders from errors
                missing_errors = [err for err in errors if "missing_placeholder" in err.lower()]
                if missing_errors:
                    # Estimate missing count from errors (conservative: assume at least 1)
                    placeholder_score = max(0.0, (len(registry) - len(missing_errors)) / len(registry))
                else:
                    # Generic placeholder error - assume partial failure
                    placeholder_score = 0.7
            issues.append("placeholder_restoration_failed")
        elif still_present > 0:
            # Placeholders still present but no errors = restoration not attempted or incomplete
            placeholder_score = (len(registry) - still_present) / len(registry)
            issues.append(f"placeholder_not_restored:{still_present}/{len(registry)}")
        else:
            # No placeholders present and no errors = restoration succeeded (perfect!)
            placeholder_score = 1.0
    # If registry is empty, no placeholders to preserve, so score is 1.0 (already set)

    # 2. Numeric accuracy
    source_nums = set(re.findall(r"\b\d+\.?\d*\b", source_text))
    translated_nums = set(re.findall(r"\b\d+\.?\d*\b", translated_text))

    numeric_score = 1.0
    if source_nums:
        preserved = len(source_nums & translated_nums)
        numeric_score = preserved / len(source_nums)
        if numeric_score < 0.9:
            issues.append(f"numeric_drift:{numeric_score:.2f}")
        elif numeric_score < 1.0:
            warnings.append(f"minor_numeric_variation:{numeric_score:.2f}")

    # 3. Format preservation
    source_bullets = len(re.findall(r"^[\s]*[-•*]\s", source_text, re.MULTILINE))
    translated_bullets = len(re.findall(r"^[\s]*[-•*]\s", translated_text, re.MULTILINE))

    source_lines = len([line for line in source_text.split("\n") if line.strip()])
    translated_lines = len([line for line in translated_text.split("\n") if line.strip()])

    format_score = 1.0
    if source_bullets > 0:
        bullet_ratio = translated_bullets / source_bullets if source_bullets > 0 else 1.0
        format_score *= min(bullet_ratio, 1.0)
        if bullet_ratio < 0.8:
            issues.append(f"format_drift:bullets_{bullet_ratio:.2f}")

    if source_lines > 0:
        line_ratio = translated_lines / source_lines if source_lines > 0 else 1.0
        if 0.7 <= line_ratio <= 1.3:
            format_score *= 1.0  # Good
        else:
            format_score *= 0.9
            if line_ratio < 0.7 or line_ratio > 1.3:
                warnings.append(f"line_count_variation:{line_ratio:.2f}")

    # 4. Fluency (heuristic)
    fluency_score = 1.0

    # Check for repeated words (sign of poor quality)
    words = translated_text.lower().split()
    if len(words) > 5:
        word_freq = {}
        for w in words:
            if len(w) > 3:  # Only count substantial words
                word_freq[w] = word_freq.get(w, 0) + 1
        max_freq = max(word_freq.values()) if word_freq else 1
        repetition_ratio = max_freq / len(words)
        if repetition_ratio > 0.3:
            fluency_score *= 0.7
            warnings.append(f"high_repetition:{repetition_ratio:.2f}")

    # Check for very short or very long translations
    len_ratio = len(translated_text) / max(len(source_text), 1)
    if len_ratio < 0.5 or len_ratio > 2.0:
        fluency_score *= 0.8
        warnings.append(f"length_ratio_unusual:{len_ratio:.2f}")

    # 5. Fidelity (proxy: length ratio within reasonable bounds)
    fidelity_score = 1.0
    if 0.8 <= len_ratio <= 1.5:
        fidelity_score = 1.0
    elif 0.6 <= len_ratio <= 2.0:
        fidelity_score = 0.9
    else:
        fidelity_score = 0.7
        issues.append(f"fidelity_concern:length_{len_ratio:.2f}")

    # Overall score (weighted average)
    # Identity score is critical - if it's 0, the overall score should be penalized heavily
    # Adjust weights based on whether placeholders exist
    has_placeholders = bool(registry)
    if has_placeholders:
        # When placeholders exist, they're critical (30% weight)
        overall_score = (
            identity_score * 0.20  # Critical: identity translations are bad
            + placeholder_score * 0.30  # Most critical after identity
            + numeric_score * 0.20
            + format_score * 0.15
            + fluency_score * 0.10
            + fidelity_score * 0.05
        )
    else:
        # When no placeholders, redistribute weight to other factors
        overall_score = (
            identity_score * 0.25  # Slightly more weight on identity
            + numeric_score * 0.25  # More weight on numeric accuracy
            + format_score * 0.20  # More weight on format
            + fluency_score * 0.15  # More weight on fluency
            + fidelity_score * 0.15  # More weight on fidelity
        )
    
    # Heavy penalty for identity translations
    if identity_score < 0.5:
        overall_score *= 0.5  # Halve the score if identity is detected

    # Determine if needs review or retry
    # More lenient thresholds for needs_review to avoid false positives
    # Identity translations always need retry (especially for headers/titles)
    # Only require placeholder_score < 0.9 for retry if there are actually placeholders to preserve
    has_placeholders = bool(registry)
    needs_retry = (
        identity_score < 0.5  # Identity translation detected
        or (has_placeholders and placeholder_score < 0.9)  # Only check if placeholders exist
        or numeric_score < 0.8 
        or (is_header and overall_score < 0.85)  # Headers need higher quality
        or len(issues) > 2
    )
    needs_review = overall_score < 0.75 or len(issues) >= 2 or identity_score < 0.7  # Flag identity issues

    # Confidence (inverse of issues)
    confidence = max(0.0, 1.0 - (len(issues) * 0.15 + len(warnings) * 0.05))

    return PostTranslationScore(
        block_id=block_id,
        overall_score=overall_score,
        placeholder_score=placeholder_score,
        numeric_score=numeric_score,
        format_score=format_score,
        fluency_score=fluency_score,
        fidelity_score=fidelity_score,
        issues=issues,
        warnings=warnings,
        needs_review=needs_review,
        needs_retry=needs_retry,
        confidence=confidence,
    )


def aggregate_scores(
    pre_scores: list[PreTranslationScore],
    post_scores: list[PostTranslationScore],
) -> dict:
    """Aggregate pre and post scores for document-level insights."""
    if not post_scores:
        return {
            "document_quality": 0.0,
            "blocks_total": 0,
            "blocks_acceptable": 0,
            "blocks_need_review": 0,
            "blocks_need_retry": 0,
        }

    # Pre-translation insights
    avg_complexity = (
        sum(s.complexity_score for s in pre_scores) / len(pre_scores) if pre_scores else 0.0
    )
    complex_blocks = sum(1 for s in pre_scores if s.is_complex())

    # Post-translation insights
    avg_quality = sum(s.overall_score for s in post_scores) / len(post_scores)
    acceptable = sum(1 for s in post_scores if s.is_acceptable())
    needs_review = sum(1 for s in post_scores if s.needs_review)
    needs_retry = sum(1 for s in post_scores if s.needs_retry)

    # Average scores by dimension
    avg_placeholder = sum(s.placeholder_score for s in post_scores) / len(post_scores)
    avg_numeric = sum(s.numeric_score for s in post_scores) / len(post_scores)
    avg_format = sum(s.format_score for s in post_scores) / len(post_scores)
    avg_fluency = sum(s.fluency_score for s in post_scores) / len(post_scores)
    avg_fidelity = sum(s.fidelity_score for s in post_scores) / len(post_scores)
    avg_confidence = sum(s.confidence for s in post_scores) / len(post_scores)

    return {
        # Document-level
        "document_quality": avg_quality,
        "document_confidence": avg_confidence,
        "blocks_total": len(post_scores),
        "blocks_acceptable": acceptable,
        "blocks_need_review": needs_review,
        "blocks_need_retry": needs_retry,
        "acceptance_rate": acceptable / len(post_scores) if post_scores else 0.0,
        # Pre-translation
        "avg_source_complexity": avg_complexity,
        "complex_blocks": complex_blocks,
        # Quality dimensions
        "avg_placeholder_preservation": avg_placeholder,
        "avg_numeric_accuracy": avg_numeric,
        "avg_format_preservation": avg_format,
        "avg_fluency": avg_fluency,
        "avg_fidelity": avg_fidelity,
        # Issues
        "total_issues": sum(len(s.issues) for s in post_scores),
        "total_warnings": sum(len(s.warnings) for s in post_scores),
    }
