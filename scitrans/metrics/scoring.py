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
        """Is this translation acceptable without review?"""
        return self.overall_score >= 0.85 and not self.needs_retry


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
) -> PostTranslationScore:
    """Assess translation quality after translation.

    Comprehensive evaluation across multiple quality dimensions.
    """
    issues = list(errors)
    warnings = []

    # 1. Placeholder preservation (critical)
    placeholder_score = 1.0
    if registry:
        present = sum(1 for ph in registry if ph in translated_text)
        placeholder_score = present / len(registry) if registry else 1.0
        if placeholder_score < 1.0:
            issues.append(f"placeholder_preservation:{placeholder_score:.2f}")

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
    overall_score = (
        placeholder_score * 0.35  # Most critical
        + numeric_score * 0.25
        + format_score * 0.20
        + fluency_score * 0.10
        + fidelity_score * 0.10
    )

    # Determine if needs review or retry
    # More lenient thresholds for needs_review to avoid false positives
    needs_retry = placeholder_score < 0.9 or numeric_score < 0.8 or len(issues) > 2
    needs_review = overall_score < 0.75 or len(issues) >= 2  # Only flag serious issues

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
