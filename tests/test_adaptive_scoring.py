"""Test pre and post-translation scoring system."""

from scitrans.metrics.scoring import (
    aggregate_scores,
    compute_post_translation_score,
    compute_pre_translation_score,
)


def test_pre_scoring_simple_text():
    """Simple text should have low complexity."""
    text = "This is a simple sentence. It has no special content."
    score = compute_pre_translation_score("b_0_test", text)

    assert score.complexity_score < 0.4
    assert not score.has_math
    assert not score.has_code
    assert score.recommended_temperature > 0.1


def test_pre_scoring_complex_math():
    """Text with math should have high complexity."""
    text = (
        "The Einstein equation $E=mc^2$ relates energy and mass. "
        "The integral $$\\int_0^\\infty e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}$$ is important."
    )
    score = compute_pre_translation_score("b_0_test", text)

    assert score.complexity_score >= 0.4  # Has math content
    assert score.has_math
    assert score.recommended_temperature <= 0.2  # Lower temp for math
    assert score.recommended_candidates >= 3  # Multiple candidates for quality


def test_pre_scoring_technical_text():
    """Technical text should have moderate complexity."""
    text = (
        "The implementation utilizes convolutional neural networks "
        "with regularization techniques and hyperparameter optimization."
    )
    score = compute_pre_translation_score("b_0_test", text)

    assert score.technical_term_density > 0.3
    assert score.complexity_score >= 0.2  # Technical terms add complexity
    assert score.avg_word_length > 6  # Long technical words


def test_post_scoring_perfect_translation():
    """Perfect translation should score highly."""
    source = "The value is 42 and the equation is placeholder."
    translated = "La valeur est 42 et l'équation est placeholder."
    registry = {}

    score = compute_post_translation_score("b_0_test", source, translated, registry, [])

    assert score.overall_score > 0.9
    assert score.placeholder_score == 1.0
    assert score.numeric_score == 1.0
    assert score.is_acceptable()
    assert not score.needs_retry


def test_post_scoring_missing_placeholder():
    """Missing placeholders should trigger retry."""
    source = "Math: <<MATH_0001>> and text."
    translated = "Math: missing and text."  # Placeholder missing!
    registry = {"<<MATH_0001>>": "$x^2$"}

    score = compute_post_translation_score(
        "b_0_test", source, translated, registry, ["missing_placeholder"]
    )

    assert score.placeholder_score < 1.0
    assert score.needs_retry
    # Check that issue is present (format varies)
    assert len(score.issues) > 0


def test_post_scoring_numeric_drift():
    """Changed numbers should be detected."""
    source = "The result is 42.5 and 123."
    translated = "Le résultat est 99 et 123."  # 42.5 changed to 99
    registry = {}

    score = compute_post_translation_score("b_0_test", source, translated, registry, [])

    assert score.numeric_score < 1.0
    assert "numeric_drift" in score.issues[0]


def test_aggregate_scores():
    """Aggregation should produce document-level metrics."""
    # Create some pre-scores
    pre_scores = [
        compute_pre_translation_score("b1", "Simple text."),
        compute_pre_translation_score("b2", "Math $x^2$ text."),
        compute_pre_translation_score("b3", "Another simple text."),
    ]

    # Create some post-scores
    post_scores = [
        compute_post_translation_score("b1", "Simple.", "Simple.", {}, []),
        compute_post_translation_score("b2", "Math $x^2$.", "Math <<M>>.", {"<<M>>": "$x^2$"}, []),
        compute_post_translation_score("b3", "Text.", "Texte.", {}, []),
    ]

    agg = aggregate_scores(pre_scores, post_scores)

    assert "document_quality" in agg
    assert "document_confidence" in agg
    assert "blocks_total" in agg
    assert agg["blocks_total"] == 3
    assert "avg_source_complexity" in agg
    assert "acceptance_rate" in agg


def test_adaptive_strategy_selection():
    """Complex blocks should get different strategies."""
    # Simple block
    simple = compute_pre_translation_score("b1", "Hello world.")
    assert simple.recommended_candidates == 3
    assert simple.recommended_constraints == "relaxed"

    # Complex block (needs very high complexity for strict mode)
    complex_text = (
        "The theorem states that $$\\sum_{n=1}^\\infty \\frac{1}{n^2} = \\frac{\\pi^2}{6}$$ "
        "with implementation using `code` and references [1,2,3]. "
        "See https://arxiv.org/abs/1234 and Table 1 for hyperparameter optimization."
    )
    complex = compute_pre_translation_score("b2", complex_text)
    # Complex blocks get stricter handling
    assert complex.complexity_score >= 0.5
    assert complex.recommended_candidates >= 3
    assert complex.recommended_temperature <= 0.2
