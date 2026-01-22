"""Test placeholder preservation during translation."""

import pytest
from scitrans.masking.engine import MaskingEngine
from scitrans.core.models import Block, Line, Span, SpanStyle, BBox


def test_math_placeholder_preservation():
    """Test that LaTeX math is masked and restored correctly."""
    masker = MaskingEngine()
    
    text = "The equation $E=mc^2$ is famous."
    masked, registry, counts = masker.mask(text)
    
    # Verify masking
    assert "MATH_INLINE" in counts
    assert counts["MATH_INLINE"] == 1
    assert "$E=mc^2$" not in masked
    assert any("MATH_INLINE" in ph for ph in registry.keys())
    
    # Simulate translation (placeholder should be preserved)
    translated = masked.replace("equation", "équation").replace("famous", "célèbre")
    
    # Verify restoration
    restored, errors = masker.restore(translated, registry)
    assert len(errors) == 0
    assert "$E=mc^2$" in restored
    assert "équation" in restored
    assert "célèbre" in restored


def test_person_name_placeholder_preservation():
    """Test that person names are masked and restored correctly."""
    masker = MaskingEngine()
    
    text = "John Smith conducted the research."
    masked, registry, counts = masker.mask(text)
    
    # Verify masking
    assert "PERSON_NAME" in counts
    assert "John Smith" not in masked
    
    # Simulate translation
    translated = masked.replace("conducted", "a mené").replace("research", "recherche")
    
    # Verify restoration
    restored, errors = masker.restore(translated, registry)
    assert len(errors) == 0
    assert "John Smith" in restored


def test_multiple_placeholders():
    """Test handling of multiple different placeholder types."""
    masker = MaskingEngine()
    
    text = "John Smith found that $E=mc^2$ at https://example.com"
    masked, registry, counts = masker.mask(text)
    
    # Verify multiple types masked
    assert len(registry) >= 3  # Name, math, URL
    assert "John Smith" not in masked
    assert "$E=mc^2$" not in masked
    assert "https://example.com" not in masked
    
    # Simulate translation
    translated = masked.replace("found that", "a découvert que").replace("at", "à")
    
    # Verify all restored
    restored, errors = masker.restore(translated, registry)
    assert len(errors) == 0
    assert "John Smith" in restored
    assert "$E=mc^2$" in restored
    assert "https://example.com" in restored


def test_placeholder_not_in_translation():
    """Test detection when placeholder is missing from translation."""
    masker = MaskingEngine()
    
    text = "The equation $E=mc^2$ is important."
    masked, registry, counts = masker.mask(text)
    
    # Simulate translation that loses the placeholder
    translated = "L'équation est importante."  # Missing placeholder!
    
    # Verify error detection
    restored, errors = masker.restore(translated, registry)
    assert len(errors) > 0
    assert any("missing_placeholder" in err for err in errors)


def test_document_structure_not_masked():
    """Test that document structure words are not masked as person names."""
    masker = MaskingEngine()
    
    # These should NOT be masked as person names
    test_cases = [
        "Small Test Document",
        "Section Introduction",
        "Chapter Results",
        "Test Report",
    ]
    
    for text in test_cases:
        masked, registry, counts = masker.mask(text)
        # Should not have PERSON_NAME placeholders
        assert "PERSON_NAME" not in counts or counts["PERSON_NAME"] == 0, f"'{text}' should not be masked as person name"
        assert text == masked or text.lower() in masked.lower(), f"'{text}' should remain mostly unchanged"


def test_actual_person_names_masked():
    """Test that actual person names ARE masked."""
    masker = MaskingEngine()
    
    # These SHOULD be masked as person names
    test_cases = [
        "John Smith",
        "Pierre Dupont",
        "Tchienkoua Franck Davy",
        "Marie Curie",
    ]
    
    for text in test_cases:
        masked, registry, counts = masker.mask(text)
        # Should have PERSON_NAME placeholders
        assert "PERSON_NAME" in counts and counts["PERSON_NAME"] > 0, f"'{text}' should be masked as person name"
        assert text not in masked, f"'{text}' should be replaced with placeholder"

