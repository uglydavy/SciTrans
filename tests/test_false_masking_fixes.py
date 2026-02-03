"""Tests for false masking fixes.

This module tests the improvements made to prevent false positive masking of:
1. Section titles and headers
2. Technical terms and academic vocabulary
3. Table headers that look like person names
4. Other common patterns that were incorrectly masked
"""

from __future__ import annotations

import pytest

from scitrans.core.models import BBox, Block, Line, Span, SpanStyle
from scitrans.masking.engine import MaskingEngine
from scitrans.parsing.layout import is_table_candidate


class TestFalsePersonNameMasking:
    """Test that technical terms and section titles are NOT masked as PERSON_NAME."""
    
    def setup_method(self):
        """Initialize masking engine for each test."""
        self.engine = MaskingEngine()
    
    def test_section_titles_not_masked(self):
        """Section titles should NOT be masked as person names."""
        test_cases = [
            "Section 1: Content Analysis",
            "Section 2: Methodology",
            "Chapter 3: Results",
            "Part 1: Introduction",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for section title: {text}"
            assert masked == text, \
                f"Section title was modified: {text} → {masked}"
    
    def test_technical_terms_not_masked(self):
        """Technical terms should NOT be masked as person names."""
        test_cases = [
            "Content Analysis",
            "Mathematical Content",
            "Computational Complexity",
            "Data Analysis",
            "Machine Learning",
            "Deep Learning",
            "Natural Language",
            "Computer Vision",
            "Statistical Analysis",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for technical term: {text}"
            assert masked == text, \
                f"Technical term was modified: {text} → {masked}"
    
    def test_research_terms_not_masked(self):
        """Research/academic terms should NOT be masked as person names."""
        test_cases = [
            "Literature Review",
            "Systematic Review",
            "Case Study",
            "Comparative Study",
            "Empirical Evidence",
            "Theoretical Framework",
            "Research Methodology",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for research term: {text}"
    
    def test_table_headers_not_masked(self):
        """Table headers should NOT be masked as person names."""
        test_cases = [
            "Method\nAccuracy\nSpeed",
            "Data Collection",
            "Performance Evaluation",
            "Experimental Results",
            "Result Summary",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for table header: {text}"
    
    def test_analysis_types_not_masked(self):
        """Analysis type terms should NOT be masked."""
        test_cases = [
            "Comparative Analysis",
            "Complexity Analysis",
            "Performance Analysis",
            "Error Analysis",
            "Risk Analysis",
            "Trend Analysis",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for analysis type: {text}"
    
    def test_terms_ending_with_keywords_not_masked(self):
        """Terms ending with technical keywords should NOT be masked."""
        test_cases = [
            "System Architecture",
            "Network Protocol",
            "Database Management",
            "Software Engineering",
            "Algorithm Design",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" not in counts, \
                f"False PERSON_NAME mask for term ending with keyword: {text}"


class TestNeverMaskGuardrails:
    """Ensure section headings and academic terms are never masked."""

    def setup_method(self):
        self.engine = MaskingEngine()

    def test_academic_headings_never_masked(self):
        test_cases = [
            "Abstract",
            "Introduction",
            "Results",
            "Discussion",
            "Conclusion",
            "References",
            "Acknowledgements",
            "Materials and Methods",
            "1. Introduction",
            "Section 2: Results",
            "Chapter 3: Conclusion",
        ]

        guarded_kinds = {"PERSON_NAME", "PLACE_NAME", "TOC_ENTRY", "FIGURE_CAPTION"}
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert masked == text, f"Guardrail altered heading: {text} → {masked}"
            assert not guarded_kinds.intersection(counts.keys()), (
                f"Guardrail failed for: {text} (counts: {counts})"
            )


class TestRealPersonNamesMasking:
    """Test that actual person names ARE still correctly masked."""
    
    def setup_method(self):
        """Initialize masking engine for each test."""
        self.engine = MaskingEngine()
    
    def test_simple_names_masked(self):
        """Simple person names should be masked."""
        test_cases = [
            "John Smith",
            "Jane Doe",
            "Alice Johnson",
            "Bob Williams",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" in counts, \
                f"Failed to mask real person name: {text}"
            assert counts["PERSON_NAME"] >= 1, \
                f"Person name not counted: {text}"
            assert masked != text, \
                f"Person name was not masked: {text}"
    
    def test_three_word_names_masked(self):
        """Three-word person names should be masked."""
        test_cases = [
            "John Paul Smith",
            "Mary Jane Watson",
            "Tchienkoua Franck Davy",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" in counts, \
                f"Failed to mask three-word name: {text}"
    
    def test_names_with_middle_initial_masked(self):
        """Names with middle initials should be masked."""
        test_cases = [
            "John T. Smith",
            "Alice M. Johnson",
            "Robert J. Williams",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" in counts, \
                f"Failed to mask name with middle initial: {text}"
    
    def test_names_in_context_masked(self):
        """Person names within sentences should be masked."""
        test_cases = [
            "The study by John Smith showed...",
            "According to Jane Doe, the results...",
            "As Alice Johnson demonstrated...",
        ]
        
        for text in test_cases:
            masked, registry, counts = self.engine.mask(text)
            assert "PERSON_NAME" in counts, \
                f"Failed to mask person name in context: {text}"


class TestBlockContextValidation:
    """Test that block metadata is used for validation."""
    
    def setup_method(self):
        """Initialize masking engine for each test."""
        self.engine = MaskingEngine()
    
    def _create_block(self, text: str, is_header: bool = False) -> Block:
        """Helper to create a test block."""
        style = SpanStyle(font="Arial", size=12.0, flags=0, color=0)
        span = Span(
            text=text,
            bbox=BBox(x0=0, y0=0, x1=100, y1=10),
            style=style,
        )
        line = Line(spans=[span], bbox=BBox(x0=0, y0=0, x1=100, y1=10))
        
        meta = {"is_header": is_header} if is_header else {}
        
        return Block(
            id="test_block",
            type="text",
            bbox=BBox(x0=0, y0=0, x1=100, y1=20),
            lines=[line],
            meta=meta
        )
    
    def test_header_blocks_not_masked(self):
        """Text in header blocks should not be masked as person names."""
        text = "Content Analysis"
        block = self._create_block(text, is_header=True)
        
        masked, registry, counts = self.engine.mask(text, block=block)
        assert "PERSON_NAME" not in counts, \
            "Header block text was masked as PERSON_NAME"
    
    def test_regular_blocks_use_validation(self):
        """Regular blocks should use validation heuristics."""
        text = "Data Analysis"
        block = self._create_block(text, is_header=False)
        
        masked, registry, counts = self.engine.mask(text, block=block)
        assert "PERSON_NAME" not in counts, \
            "Technical term in regular block was masked"


class TestTableDetectionImprovements:
    """Test improved table detection to reduce false positives."""
    
    def _create_text_block(self, text: str, is_header: bool = False) -> Block:
        """Helper to create a text block for testing."""
        style = SpanStyle(font="Arial", size=12.0, flags=0, color=0)
        spans = []
        lines = []
        
        for line_text in text.split('\n'):
            span = Span(
                text=line_text,
                bbox=BBox(x0=0, y0=0, x1=100, y1=10),
                style=style,
            )
            line = Line(spans=[span], bbox=BBox(x0=0, y0=0, x1=100, y1=10))
            lines.append(line)
        
        meta = {"is_header": is_header} if is_header else {}
        
        return Block(
            id="test_block",
            type="text",
            bbox=BBox(x0=0, y0=0, x1=100, y1=len(lines) * 10),
            lines=lines,
            meta=meta
        )
    
    def test_section_titles_not_tables(self):
        """Section titles should NOT be detected as tables."""
        test_cases = [
            "Section 1: Introduction",
            "Chapter 2: Methodology",
            "Part 3: Results",
        ]
        
        for text in test_cases:
            block = self._create_text_block(text)
            assert not is_table_candidate(block), \
                f"Section title incorrectly detected as table: {text}"
    
    def test_short_headers_not_tables(self):
        """Short headers should NOT be detected as tables."""
        test_cases = [
            "Content Analysis",
            "Method",
            "Results:",
            "Discussion:",
        ]
        
        for text in test_cases:
            block = self._create_text_block(text)
            assert not is_table_candidate(block), \
                f"Short header incorrectly detected as table: {text}"
    
    def test_table_with_pipes_detected(self):
        """Tables with pipe separators should be detected."""
        text = "Column 1 | Column 2 | Column 3\nValue 1 | Value 2 | Value 3"
        block = self._create_text_block(text)
        assert is_table_candidate(block), \
            "Table with pipes was not detected"
    
    def test_table_with_tabs_detected(self):
        """Tables with tab separators should be detected."""
        text = "Column 1\tColumn 2\tColumn 3\nValue 1\tValue 2\tValue 3"
        block = self._create_text_block(text)
        assert is_table_candidate(block), \
            "Table with tabs was not detected"
    
    def test_table_with_many_numbers_detected(self):
        """Tables with high numeric density should be detected."""
        text = "12.3  45.6  78.9  10.1\n23.4  56.7  89.0  20.2\n34.5  67.8  90.1  30.3"
        block = self._create_text_block(text)
        assert is_table_candidate(block), \
            "Numeric table was not detected"
    
    def test_single_line_with_few_numbers_not_table(self):
        """Single line with only 2-3 numbers should NOT be table."""
        test_cases = [
            "Section 2: Chapter 3",
            "Page 12 of 45",
            "Version 1.2",
        ]
        
        for text in test_cases:
            block = self._create_text_block(text)
            assert not is_table_candidate(block), \
                f"Single line with few numbers incorrectly detected as table: {text}"
    
    def test_header_blocks_not_tables(self):
        """Blocks marked as headers should never be tables."""
        text = "Method  Accuracy  Speed"
        block = self._create_text_block(text, is_header=True)
        assert not is_table_candidate(block), \
            "Header block was incorrectly detected as table"


class TestMaskingRejectionLogging:
    """Test that rejected masks are properly logged (integration test)."""
    
    def setup_method(self):
        """Initialize masking engine for each test."""
        self.engine = MaskingEngine()
    
    def test_rejected_masks_dont_appear_in_output(self):
        """Rejected masks should not appear in the masked text."""
        text = "Section 1: Content Analysis with John Smith"
        block = None  # No block context
        
        masked, registry, counts = self.engine.mask(text, block=block)
        
        # "Content Analysis" should be rejected, not masked
        assert "Content Analysis" in masked, \
            "Rejected technical term should remain in text"
        
        # "John Smith" should be masked
        assert "PERSON_NAME" in counts, \
            "Real person name should be masked"
        assert "John Smith" not in masked, \
            "Real person name should be replaced with placeholder"
    
    def test_registry_only_contains_accepted_masks(self):
        """Registry should only contain actually masked items."""
        text = "Data Analysis by Alice Johnson"
        block = None
        
        masked, registry, counts = self.engine.mask(text, block=block)
        
        # Check registry doesn't contain "Data Analysis"
        for original_text in registry.values():
            assert original_text != "Data Analysis", \
                "Rejected mask should not be in registry"
        
        # Check registry contains "Alice Johnson"
        person_name_found = False
        for original_text in registry.values():
            if "Alice Johnson" in original_text or original_text == "Alice Johnson":
                person_name_found = True
                break
        
        assert person_name_found, \
            "Real person name should be in registry"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
