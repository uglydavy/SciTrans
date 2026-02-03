from __future__ import annotations

import re
from dataclasses import dataclass


# Instruction spillover keywords that should NEVER appear in translations
SPILLOVER_PATTERNS = [
    "placeholder", "conserver", "mémorisez", "rappelez-vous",
    "critique", "critical", "do not", "ne pas", "forbidden", "interdit",
    "must", "should", "required", "mandatory", "obligatoire",
    "conserve", "remember", "retain", "preserve exactly",
]


def has_instruction_spillover(text: str) -> bool:
    """Check if translation contains instruction spillover (hallucination indicator).
    
    Returns True if any instruction keywords are found in the text.
    """
    text_lower = text.lower()
    for pattern in SPILLOVER_PATTERNS:
        if pattern in text_lower:
            return True
    return False


@dataclass(frozen=True)
class RerankScore:
    """Quality score components for translation candidates."""

    placeholder_preservation: float  # 1.0 if all present, 0.0 if any missing
    glossary_compliance: float  # 0.0-1.0 based on glossary term matches
    numeric_stability: float  # 0.0-1.0 based on number preservation
    format_stability: float  # 0.0-1.0 based on bullet/line-break preservation
    semantic_similarity: float = 1.0  # 0.0-1.0 based on structure/semantic preservation
    identity_penalty: float = 1.0  # 0.0-1.0 penalty for identity translations
    length_ratio: float = 1.0  # 0.0-1.0 penalty for unusual length ratios
    spillover_penalty: float = 1.0  # 0.0-1.0 penalty for instruction spillover
    hallucinated_placeholders: float = 1.0  # 0.0-1.0 penalty for extra placeholders
    total: float = 0.0  # Weighted sum

    def is_valid(self) -> bool:
        """A candidate is invalid if placeholders are missing (hard gate)."""
        return self.placeholder_preservation >= 1.0


def score_placeholder_preservation(candidate: str, registry: dict[str, str]) -> float:
    """Score: 1.0 if all placeholders present, 0.0 if any missing."""
    if not registry:
        return 1.0
    present = sum(1 for ph in registry.keys() if ph in candidate)
    return present / len(registry) if registry else 1.0


def score_glossary_compliance(
    source: str,
    candidate: str,
    glossary: dict[str, str] | None,
) -> float:
    """Score: fraction of relevant glossary terms correctly translated."""
    if not glossary or not source.strip():
        return 1.0

    source_lower = source.lower()
    relevant = [
        (s, t) for s, t in glossary.items() if s and s.lower() in source_lower
    ]
    if not relevant:
        return 1.0

    correct = 0
    for _source_term, target_term in relevant:
        if target_term.lower() in candidate.lower():
            correct += 1

    return correct / len(relevant)


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


def score_identity_penalty(source: str, candidate: str) -> float:
    """Heavily penalize identity translations (source returned unchanged).
    
    Returns:
        1.0 if clearly different from source
        0.1 if highly similar (>85% similarity = identity translation)
        Value between 0.1-1.0 based on similarity
    """
    if not source or not candidate:
        return 1.0
    
    # Normalize for comparison
    source_norm = " ".join(source.lower().split())
    cand_norm = " ".join(candidate.lower().split())
    
    # Calculate similarity
    from difflib import SequenceMatcher
    similarity = SequenceMatcher(None, source_norm, cand_norm).ratio()
    
    # Heavy penalty for high similarity (identity translation)
    if similarity > 0.85:
        return 0.1  # 90% penalty
    elif similarity > 0.75:
        return 0.3  # 70% penalty  
    elif similarity > 0.65:
        return 0.6  # 40% penalty
    
    return 1.0  # No penalty


def score_length_ratio(source: str, candidate: str) -> float:
    """Penalize unusual length ratios (hallucination indicator).
    
    Typical expansions:
    - English→French: ~15-20% longer
    - English→German: ~10-15% longer
    
    Returns:
        1.0 if length ratio is reasonable (0.7-1.5x)
        0.3 if ratio is extreme (>2x or <0.5x) - likely hallucination
        Value between 0.3-1.0 for unusual ratios
    """
    if not source:
        return 1.0
    
    ratio = len(candidate) / len(source)
    
    # Extreme ratios indicate hallucination or truncation
    if ratio > 2.5 or ratio < 0.4:
        return 0.2  # 80% penalty - very likely hallucination
    elif ratio > 2.0 or ratio < 0.5:
        return 0.3  # 70% penalty - likely hallucination
    elif ratio > 1.8 or ratio < 0.6:
        return 0.6  # 40% penalty - unusual but possible
    elif ratio > 1.5 or ratio < 0.7:
        return 0.8  # 20% penalty - slightly unusual
    
    return 1.0  # No penalty


def score_spillover_penalty(candidate: str) -> float:
    """Penalize instruction spillover (hallucination indicator).
    
    Checks if translation contains instruction keywords that should NEVER
    appear in actual translations (e.g., "placeholder", "critical", "must").
    
    Returns:
        1.0 if no spillover detected
        0.2 if spillover detected (80% penalty)
    """
    if has_instruction_spillover(candidate):
        return 0.2  # 80% penalty for instruction spillover
    return 1.0  # No penalty


def _extract_placeholders(text: str) -> set[str]:
    patterns = [
        r"@@SCITRANS_[A-Z0-9_]+_\d{4}_[A-F0-9]{8}@@",
        r"<<[^<>]+>>",
        r"⟦[^⟦⟧]+⟧",
    ]
    matches: set[str] = set()
    for pat in patterns:
        matches.update(re.findall(pat, text))
    return matches


def score_hallucinated_placeholders(candidate: str, registry: dict[str, str]) -> float:
    """Penalize placeholders that are not in the registry."""
    placeholders = _extract_placeholders(candidate)
    if not placeholders:
        return 1.0
    if not registry:
        return 0.2
    extra = [ph for ph in placeholders if ph not in registry]
    if extra:
        return 0.2
    return 1.0


def score_semantic_similarity(source: str, candidate: str, is_header: bool = False) -> float:
    """Score how well translation matches source structure and semantics.
    
    Checks:
    1. Section/Chapter numbering preservation (e.g., "Section 1: Title" → "Section 1: Titre")
    2. Length ratio (French ~15% longer than English, shouldn't be >2x or <0.5x)
    3. Structure preservation (colons, parentheses, dashes)
    
    Returns:
        Score from 0.0 to 1.0, where 1.0 is perfect preservation
    """
    if not source.strip() or not candidate.strip():
        return 0.5
    
    score = 1.0
    
    # Check if source has section/chapter pattern
    section_pattern = r'^(Section|Chapter|Part|Appendix)\s+(\d+|[IVX]+)[:\s]+'
    source_match = re.match(section_pattern, source.strip(), re.IGNORECASE)
    
    if source_match and is_header:
        # Source has section structure - candidate should preserve it
        keyword, number = source_match.groups()
        
        # Check if candidate has similar structure (allowing translation of keyword)
        # French: Section → Section, Chapter → Chapitre, Part → Partie, Appendix → Annexe
        candidate_pattern = r'^(Section|Chapitre|Chapter|Partie|Part|Annexe|Appendix)\s+(\d+|[IVX]+)[:\s]+'
        candidate_match = re.match(candidate_pattern, candidate.strip(), re.IGNORECASE)
        
        if not candidate_match:
            # Missing section structure - major penalty
            score -= 0.6
        else:
            # Check if number is preserved
            cand_number = candidate_match.group(2)
            if cand_number != number:
                # Number changed - penalty
                score -= 0.3
    
    # Check length ratio (reasonable expansion/contraction)
    length_ratio = len(candidate) / len(source) if source else 1.0
    if length_ratio < 0.5 or length_ratio > 2.5:
        # Extreme length change - likely wrong translation
        score -= 0.4
    elif length_ratio < 0.7 or length_ratio > 1.8:
        # Unusual length change - moderate penalty
        score -= 0.2
    
    # Check structure preservation (colons, parentheses, dashes)
    source_has_colon = ':' in source
    candidate_has_colon = ':' in candidate
    if source_has_colon != candidate_has_colon:
        score -= 0.1
    
    # Check for completely unrelated content (word overlap)
    # This catches cases like "Section 1: Introduction" → "Document layout result"
    source_words = set(re.findall(r'\w+', source.lower()))
    candidate_words = set(re.findall(r'\w+', candidate.lower()))
    
    # Remove common words that translate directly
    common_numbers = {'1', '2', '3', '4', '5', '6', '7', '8', '9', '0'}
    source_words -= common_numbers
    candidate_words -= common_numbers
    
    if source_words and candidate_words:
        # Calculate overlap (allowing for translation)
        # For headers, we expect low overlap (translation changes words)
        # But if overlap is 0 and source is short, it's suspicious
        if len(source_words) <= 5:  # Short header
            # For short headers, complete lack of overlap is suspicious
            # (e.g., "Section 1: Introduction" and "Document layout result" have no overlap)
            if not (source_words & candidate_words):
                # Check if it looks like random/unrelated content
                suspicious_words = {'result', 'résultat', 'document', 'layout', 'mise', 'page', 'en'}
                if candidate_words & suspicious_words:
                    # Contains suspicious generic words - likely wrong translation
                    score -= 0.5
    
    return max(0.0, score)


def rerank_candidates(
    candidates: list[str],
    source_text: str,
    registry: dict[str, str],
    glossary: dict[str, str] | None = None,
    *,
    weights: dict[str, float] | None = None,
    backend_quality_bonus: dict[str, float] | None = None,
    is_header: bool = False,
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
        "semantic_similarity": 4.0,  # Semantic/structure preservation
        "identity_penalty": 8.0,  # NEW: Identity translation detection (critical)
        "length_ratio": 3.0,  # NEW: Hallucination detection via length
        "spillover_penalty": 6.0,  # NEW: Instruction spillover detection
        "hallucinated_placeholders": 6.0,  # NEW: Extra placeholders not in registry
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
        # Original scoring dimensions
        ph_score = score_placeholder_preservation(candidate, registry)
        gloss_score = score_glossary_compliance(source_text, candidate, glossary)
        num_score = score_numeric_stability(source_text, candidate)
        fmt_score = score_format_stability(source_text, candidate)
        sem_score = score_semantic_similarity(source_text, candidate, is_header=is_header)
        
        # NEW: Additional scoring dimensions for quality
        identity_score = score_identity_penalty(source_text, candidate)
        length_score = score_length_ratio(source_text, candidate)
        spillover_score = score_spillover_penalty(candidate)
        hallucinated_score = score_hallucinated_placeholders(candidate, registry)

        # Calculate weighted total
        base_total = (
            ph_score * w["placeholder_preservation"]
            + gloss_score * w["glossary_compliance"]
            + num_score * w["numeric_stability"]
            + fmt_score * w["format_stability"]
            + sem_score * w.get("semantic_similarity", 4.0)
            + identity_score * w.get("identity_penalty", 8.0)  # NEW
            + length_score * w.get("length_ratio", 3.0)  # NEW
            + spillover_score * w.get("spillover_penalty", 6.0)  # NEW
            + hallucinated_score * w.get("hallucinated_placeholders", 6.0)  # NEW
        )

        # Apply quality bonus based on candidate position (earlier = higher quality backend)
        # For cascade_free: first candidate is Ollama, last is Google
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
            semantic_similarity=sem_score,
            identity_penalty=identity_score,  # NEW
            length_ratio=length_score,  # NEW
            spillover_penalty=spillover_score,  # NEW
            hallucinated_placeholders=hallucinated_score,  # NEW
            total=total,
        )
        scored.append((candidate, score))

    # Sort by total score (descending), but prioritize valid candidates
    scored.sort(key=lambda x: (not x[1].is_valid(), -x[1].total))

    return scored
