from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RerankScore:
    """Quality score components for translation candidates."""

    placeholder_preservation: float  # 1.0 if all present, 0.0 if any missing
    glossary_compliance: float  # 0.0-1.0 based on glossary term matches
    numeric_stability: float  # 0.0-1.0 based on number preservation
    format_stability: float  # 0.0-1.0 based on bullet/line-break preservation
    total: float  # Weighted sum

    def is_valid(self) -> bool:
        """A candidate is invalid if placeholders are missing (hard gate)."""
        return self.placeholder_preservation >= 1.0


def score_placeholder_preservation(candidate: str, registry: dict[str, str]) -> float:
    """Score: 1.0 if all placeholders present, 0.0 if any missing."""
    if not registry:
        return 1.0
    present = sum(1 for ph in registry.keys() if ph in candidate)
    return present / len(registry) if registry else 1.0


def score_glossary_compliance(candidate: str, glossary: dict[str, str] | None) -> float:
    """Score: fraction of glossary terms correctly translated."""
    if not glossary:
        return 1.0

    correct = 0
    total = 0
    for source_term, target_term in glossary.items():
        if not source_term.strip():
            continue
        total += 1
        # Check if target term appears in candidate (case-insensitive)
        if target_term.lower() in candidate.lower():
            correct += 1

    return correct / total if total > 0 else 1.0


def extract_numbers(text: str) -> list[str]:
    """Extract numeric patterns from text."""
    # Match numbers (integers, decimals, scientific notation)
    pattern = r"\b\d+\.?\d*(?:[eE][+-]?\d+)?\b"
    return re.findall(pattern, text)


def score_numeric_stability(source: str, candidate: str) -> float:
    """Score: fraction of numbers preserved (allowing minor formatting changes)."""
    source_nums = extract_numbers(source)
    candidate_nums = extract_numbers(candidate)

    if not source_nums:
        return 1.0

    # Normalize numbers for comparison (remove leading zeros, etc.)
    def normalize(n: str) -> str:
        try:
            return str(float(n))
        except ValueError:
            return n

    source_normalized = {normalize(n) for n in source_nums}
    candidate_normalized = {normalize(n) for n in candidate_nums}

    # Count how many source numbers appear in candidate
    preserved = len(source_normalized & candidate_normalized)
    return preserved / len(source_normalized) if source_normalized else 1.0


def score_format_stability(source: str, candidate: str) -> float:
    """Score: preservation of bullets, line breaks, indentation markers."""
    # Count bullets in source and candidate
    source_bullets = len(re.findall(r"^[\s]*[-•*]\s", source, re.MULTILINE))
    candidate_bullets = len(re.findall(r"^[\s]*[-•*]\s", candidate, re.MULTILINE))

    # Count line breaks
    source_lines = len([line for line in source.split("\n") if line.strip()])
    candidate_lines = len([line for line in candidate.split("\n") if line.strip()])

    bullet_score = 1.0
    if source_bullets > 0:
        bullet_score = min(candidate_bullets / source_bullets, 1.0) if source_bullets > 0 else 1.0

    line_score = 1.0
    if source_lines > 0:
        line_score = min(candidate_lines / source_lines, 1.0) if source_lines > 0 else 1.0

    # Weighted average
    return bullet_score * 0.5 + line_score * 0.5


def rerank_candidates(
    candidates: list[str],
    source_text: str,
    registry: dict[str, str],
    glossary: dict[str, str] | None = None,
    *,
    weights: dict[str, float] | None = None,
    backend_quality_bonus: dict[str, float] | None = None,
) -> list[tuple[str, RerankScore]]:
    """Rerank translation candidates by quality scores.

    Returns list of (candidate, score) tuples sorted by total score (descending).

    Args:
        candidates: List of translation candidates
        source_text: Original source text
        registry: Placeholder registry
        glossary: Optional glossary for domain terms
        weights: Optional custom weights for scoring
        backend_quality_bonus: Optional bonus scores by backend (e.g., {"deepseek": 2.0, "google": -1.0})
    """
    if not candidates:
        return []

    default_weights = {
        "placeholder_preservation": 10.0,  # Hard gate (high weight)
        "glossary_compliance": 3.0,
        "numeric_stability": 2.0,
        "format_stability": 1.0,
    }
    w = weights or default_weights

    # Quality bonuses: prefer DeepSeek/Ollama, penalize Google Translate
    default_quality_bonus = {
        "deepseek": 2.0,  # High quality bonus
        "ollama": 1.5,  # Good quality bonus
        "google": -1.0,  # Penalty for low quality (free tier)
    }
    # Note: quality_bonus is available for future use
    _quality_bonus = backend_quality_bonus or default_quality_bonus

    scored: list[tuple[str, RerankScore]] = []

    for idx, candidate in enumerate(candidates):
        ph_score = score_placeholder_preservation(candidate, registry)
        gloss_score = score_glossary_compliance(candidate, glossary)
        num_score = score_numeric_stability(source_text, candidate)
        fmt_score = score_format_stability(source_text, candidate)

        base_total = (
            ph_score * w["placeholder_preservation"]
            + gloss_score * w["glossary_compliance"]
            + num_score * w["numeric_stability"]
            + fmt_score * w["format_stability"]
        )

        # Apply quality bonus based on candidate position (earlier = higher quality backend)
        # For cascade_free: first candidate is DeepSeek, last is Google
        quality_adjustment = 0.0
        if len(candidates) > 1:
            # Earlier candidates (from better backends) get bonus
            position_bonus = (len(candidates) - idx) * 0.5
            quality_adjustment = position_bonus

        total = base_total + quality_adjustment

        score = RerankScore(
            placeholder_preservation=ph_score,
            glossary_compliance=gloss_score,
            numeric_stability=num_score,
            format_stability=fmt_score,
            total=total,
        )
        scored.append((candidate, score))

    # Sort by total score (descending), but prioritize valid candidates
    scored.sort(key=lambda x: (not x[1].is_valid(), -x[1].total))

    return scored
