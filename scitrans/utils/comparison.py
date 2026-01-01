"""
Translation Comparison Utilities

Provides side-by-side comparison of source and translated text.
"""

from __future__ import annotations

import difflib
import logging

logger = logging.getLogger(__name__)


def compare_translations(
    source_text: str, translated_text: str, context_lines: int = 3
) -> dict[str, any]:
    """
    Compare source and translated text with diff highlighting.

    Args:
        source_text: Original source text
        translated_text: Translated text
        context_lines: Number of context lines around differences

    Returns:
        Dictionary with comparison data
    """
    source_lines = source_text.splitlines()
    translated_lines = translated_text.splitlines()

    # Generate unified diff
    diff = list(difflib.unified_diff(source_lines, translated_lines, lineterm="", n=context_lines))

    # Calculate similarity
    similarity = difflib.SequenceMatcher(None, source_text.lower(), translated_text.lower()).ratio()

    # Count differences
    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    return {
        "similarity": similarity,
        "diff_lines": diff,
        "added_lines": added,
        "removed_lines": removed,
        "source_length": len(source_text),
        "translated_length": len(translated_text),
        "length_ratio": len(translated_text) / len(source_text) if source_text else 0,
    }


def format_comparison_html(comparison_data: dict) -> str:
    """Format comparison data as HTML for display."""
    html = f"""
    <div class="comparison-container">
        <h3>Translation Comparison</h3>
        <div class="metrics">
            <p><strong>Similarity:</strong> {comparison_data["similarity"]:.1%}</p>
            <p><strong>Length Ratio:</strong> {comparison_data["length_ratio"]:.2f}</p>
            <p><strong>Source Length:</strong> {comparison_data["source_length"]} chars</p>
            <p><strong>Translated Length:</strong> {comparison_data["translated_length"]} chars</p>
        </div>
        <div class="diff">
            <pre>{chr(10).join(comparison_data["diff_lines"])}</pre>
        </div>
    </div>
    """
    return html
