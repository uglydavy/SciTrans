"""Test reranking functionality."""

from scitrans.translation.reranking import (
    extract_numbers,
    rerank_candidates,
    score_glossary_compliance,
    score_numeric_stability,
    score_placeholder_preservation,
)


def test_placeholder_preservation_scoring():
    """Placeholder preservation should score 1.0 if all present."""
    registry = {"<<MATH_0001>>": "$E=mc^2$", "<<URL_0001>>": "https://example.com"}

    # All present
    candidate1 = "This is <<MATH_0001>> and <<URL_0001>>"
    score1 = score_placeholder_preservation(candidate1, registry)
    assert score1 == 1.0

    # One missing
    candidate2 = "This is <<MATH_0001>> only"
    score2 = score_placeholder_preservation(candidate2, registry)
    assert score2 == 0.5

    # All missing
    candidate3 = "No placeholders"
    score3 = score_placeholder_preservation(candidate3, registry)
    assert score3 == 0.0


def test_glossary_compliance_scoring():
    """Glossary compliance should detect correct translations."""
    glossary = {
        "machine learning": "apprentissage automatique",
        "neural network": "réseau de neurones",
    }

    # Both terms present
    candidate1 = "L'apprentissage automatique et le réseau de neurones"
    score1 = score_glossary_compliance(candidate1, glossary)
    assert score1 == 1.0

    # One term present
    candidate2 = "L'apprentissage automatique seulement"
    score2 = score_glossary_compliance(candidate2, glossary)
    assert score2 == 0.5

    # No terms
    candidate3 = "Quelque chose d'autre"
    score3 = score_glossary_compliance(candidate3, glossary)
    assert score3 == 0.0


def test_numeric_stability():
    """Numbers should be preserved in translation."""
    source = "The result is 42.5 and 123"

    # All numbers preserved
    candidate1 = "Le résultat est 42.5 et 123"
    score1 = score_numeric_stability(source, candidate1)
    assert score1 == 1.0

    # One number missing
    candidate2 = "Le résultat est 42.5 seulement"
    score2 = score_numeric_stability(source, candidate2)
    assert score2 == 0.5


def test_extract_numbers():
    """Extract numbers from text."""
    text = "The values are 42, 3.14, and 1.5e-3"
    numbers = extract_numbers(text)
    assert "42" in numbers
    assert "3.14" in numbers
    assert "1.5e-3" in numbers


def test_rerank_candidates():
    """Reranking should prioritize valid candidates."""
    candidates = [
        "Translation without placeholders",
        "Translation with <<MATH_0001>> preserved",
        "Another one <<MATH_0001>>",
    ]
    source = "Source with math"
    registry = {"<<MATH_0001>>": "$x^2$"}

    ranked = rerank_candidates(candidates, source, registry)

    # Should have 3 results
    assert len(ranked) == 3

    # Valid candidates (with placeholders) should be first
    best_candidate, best_score = ranked[0]
    assert "<<MATH_0001>>" in best_candidate
    assert best_score.is_valid()
