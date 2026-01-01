"""Test health scoring system."""

from scitrans.core.models import BBox, Block, TranslatedBlock
from scitrans.metrics.health import compute_block_health


def test_healthy_block():
    """A perfect translation should score as healthy."""
    block = Block(
        id="b_0_test",
        type="text",
        bbox=BBox(x0=0, y0=0, x1=100, y1=50),
        lines=[],
    )

    translated = TranslatedBlock(
        block_id="b_0_test",
        source_text="Hello 123",
        translated_text="Bonjour 123",
        ok=True,
        errors=[],
    )

    health = compute_block_health(
        block=block,
        translated_block=translated,
        registry={},
    )

    assert health.status == "ok"
    assert health.score >= 0.9
    assert len(health.reason_codes) == 0


def test_missing_placeholder():
    """Missing placeholders should mark block as failed."""
    block = Block(
        id="b_0_test",
        type="text",
        bbox=BBox(x0=0, y0=0, x1=100, y1=50),
        lines=[],
    )

    translated = TranslatedBlock(
        block_id="b_0_test",
        source_text="Hello <<MATH_0001>>",
        translated_text="Bonjour only",  # Missing placeholder
        ok=False,
        errors=["missing_placeholder:<<MATH_0001>>"],
    )

    registry = {"<<MATH_0001>>": "$x^2$"}

    health = compute_block_health(
        block=block,
        translated_block=translated,
        registry=registry,
    )

    assert health.status == "failed"
    assert "placeholder_missing" in health.reason_codes


def test_numeric_drift():
    """Numeric changes should be flagged."""
    block = Block(
        id="b_0_test",
        type="text",
        bbox=BBox(x0=0, y0=0, x1=100, y1=50),
        lines=[],
    )

    translated = TranslatedBlock(
        block_id="b_0_test",
        source_text="The value is 42.5",
        translated_text="La valeur est 99",  # Number changed
        ok=True,
        errors=[],
    )

    health = compute_block_health(
        block=block,
        translated_block=translated,
        registry={},
    )

    assert "numeric_drift" in health.reason_codes
    assert health.score < 0.9
