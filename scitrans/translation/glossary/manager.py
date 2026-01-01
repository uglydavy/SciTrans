"""
Centralized Glossary Management for SciTrans-LLMs.

This module provides a unified interface for loading, managing, and enforcing
domain-specific glossaries across translation workflows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GlossaryTerm:
    """A single glossary term with metadata."""

    source: str
    target: str
    domain: str = "general"
    confidence: float = 1.0
    case_sensitive: bool = False

    def matches(self, text: str) -> bool:
        """Check if this term appears in text."""
        if self.case_sensitive:
            return self.source in text
        return self.source.lower() in text.lower()


@dataclass
class GlossaryStats:
    """Statistics about glossary usage."""

    total_terms: int = 0
    terms_found: int = 0
    terms_enforced: int = 0
    terms_violated: int = 0
    adherence_rate: float = 0.0

    def calculate_adherence(self) -> float:
        """Calculate adherence rate (0-1)."""
        if self.terms_found == 0:
            return 1.0  # No terms expected, 100% adherence
        self.adherence_rate = self.terms_enforced / self.terms_found
        return self.adherence_rate


class GlossaryManager:
    """
    Centralized glossary management system.

    Features:
    - Load glossaries from JSON files or dictionaries
    - Multi-domain support (ML, physics, biology, etc.)
    - Prompt injection for translation
    - Post-translation validation
    - Adherence metrics
    """

    def __init__(self, glossary_dir: Path | None = None):
        """
        Initialize glossary manager.

        Args:
            glossary_dir: Directory containing glossary JSON files.
                         Defaults to scitran/translation/glossary/domains/
        """
        self.glossary_dir = glossary_dir or self._get_default_glossary_dir()
        self.terms: dict[str, GlossaryTerm] = {}
        self.domains_loaded: set[str] = set()

        # Create glossary directory if it doesn't exist
        self.glossary_dir.mkdir(parents=True, exist_ok=True)

    def _get_default_glossary_dir(self) -> Path:
        """Get default glossary directory."""
        return Path(__file__).parent / "domains"

    def load_domain(self, domain: str, direction: str = "en-fr") -> int:
        """
        Load glossary for a specific domain.

        Args:
            domain: Domain name (ml, physics, biology, etc.)
            direction: Translation direction (en-fr, fr-en)

        Returns:
            Number of terms loaded
        """
        glossary_file = self.glossary_dir / f"{domain}_{direction.replace('-', '_')}.json"

        if not glossary_file.exists():
            logger.warning(f"Glossary file not found: {glossary_file}")
            return 0

        try:
            with open(glossary_file, encoding="utf-8") as f:
                data = json.load(f)

            terms_data = data.get("terms", data)  # Support both formats
            count = 0

            for source, target in terms_data.items():
                term = GlossaryTerm(source=source, target=target, domain=domain)
                self.terms[source.lower()] = term
                count += 1

            self.domains_loaded.add(domain)
            logger.info(f"Loaded {count} terms from {domain} ({direction})")
            return count

        except Exception as e:
            logger.error(f"Error loading glossary {glossary_file}: {e}")
            return 0

    def load_from_dict(self, terms: dict[str, str], domain: str = "custom") -> int:
        """
        Load glossary from a dictionary.

        Args:
            terms: Dictionary of source -> target terms
            domain: Domain label for these terms

        Returns:
            Number of terms loaded
        """
        count = 0
        for source, target in terms.items():
            term = GlossaryTerm(source=source, target=target, domain=domain)
            self.terms[source.lower()] = term
            count += 1

        self.domains_loaded.add(domain)
        logger.info(f"Loaded {count} terms from dictionary ({domain})")
        return count

    def load_from_file(self, filepath: Path) -> int:
        """
        Load glossary from a JSON file.

        Args:
            filepath: Path to JSON file with terms

        Returns:
            Number of terms loaded
        """
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)

            terms = data.get("terms", data)
            domain = data.get("domain", "imported")

            return self.load_from_dict(terms, domain)

        except Exception as e:
            logger.error(f"Error loading glossary from {filepath}: {e}")
            return 0

    def add_term(self, source: str, target: str, domain: str = "user") -> None:
        """Add a single term to the glossary."""
        term = GlossaryTerm(source=source, target=target, domain=domain)
        self.terms[source.lower()] = term

    def get_term(self, source: str) -> GlossaryTerm | None:
        """Get a term by source text (case-insensitive)."""
        return self.terms.get(source.lower())

    def get_translation(self, source: str) -> str | None:
        """Get translation for a term (case-insensitive)."""
        term = self.get_term(source)
        return term.target if term else None

    def find_terms_in_text(self, text: str) -> list[GlossaryTerm]:
        """
        Find all glossary terms present in text.

        Args:
            text: Text to search

        Returns:
            List of terms found in text
        """
        found = []
        text_lower = text.lower()

        for term in self.terms.values():
            if term.source.lower() in text_lower:
                found.append(term)

        return found

    def generate_prompt_section(self, source_text: str, max_terms: int = 20) -> str:
        """
        Generate glossary section for translation prompt.

        Args:
            source_text: Source text to be translated
            max_terms: Maximum number of terms to include

        Returns:
            Formatted glossary section for prompt
        """
        # Find relevant terms in source text
        relevant_terms = self.find_terms_in_text(source_text)

        if not relevant_terms:
            return ""

        # Limit to max_terms
        relevant_terms = relevant_terms[:max_terms]

        # Format as bullet list
        lines = ["Use these terminology translations:"]
        for term in relevant_terms:
            lines.append(f'  • "{term.source}" → "{term.target}"')

        return "\n".join(lines)

    def validate_translation(self, source_text: str, translated_text: str) -> GlossaryStats:
        """
        Validate that glossary terms were correctly translated.

        Args:
            source_text: Original source text
            translated_text: Translated text

        Returns:
            GlossaryStats with adherence metrics
        """
        stats = GlossaryStats()

        # Find terms in source
        source_terms = self.find_terms_in_text(source_text)
        stats.total_terms = len(self.terms)
        stats.terms_found = len(source_terms)

        if not source_terms:
            stats.adherence_rate = 1.0
            return stats

        # Check if expected translations appear in target
        translated_lower = translated_text.lower()

        for term in source_terms:
            expected_translation = term.target.lower()
            if expected_translation in translated_lower:
                stats.terms_enforced += 1
            else:
                stats.terms_violated += 1
                logger.debug(
                    f"Glossary violation: '{term.source}' should translate to "
                    f"'{term.target}', not found in output"
                )

        stats.calculate_adherence()
        return stats

    def get_stats(self) -> dict[str, any]:
        """Get glossary statistics."""
        return {
            "total_terms": len(self.terms),
            "domains_loaded": list(self.domains_loaded),
            "domain_counts": self._count_by_domain(),
        }

    def _count_by_domain(self) -> dict[str, int]:
        """Count terms by domain."""
        counts = {}
        for term in self.terms.values():
            counts[term.domain] = counts.get(term.domain, 0) + 1
        return counts

    def clear(self) -> None:
        """Clear all loaded terms."""
        self.terms.clear()
        self.domains_loaded.clear()
        logger.info("Glossary cleared")

    def export_to_file(self, filepath: Path, domain: str | None = None) -> None:
        """
        Export glossary to JSON file.

        Args:
            filepath: Output file path
            domain: If specified, only export terms from this domain
        """
        terms_to_export = {}

        for _source_key, term in self.terms.items():
            if domain and term.domain != domain:
                continue
            terms_to_export[term.source] = term.target

        data = {
            "domain": domain or "all",
            "total_terms": len(terms_to_export),
            "terms": terms_to_export,
        }

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Exported {len(terms_to_export)} terms to {filepath}")

    def to_dict(self) -> dict[str, str]:
        """Export all terms as simple dictionary."""
        return {term.source: term.target for term in self.terms.values()}

    def get_glossary_dict(self) -> dict[str, str]:
        """Get glossary as dictionary (alias for to_dict for compatibility)."""
        return self.to_dict()

    def __len__(self) -> int:
        """Return number of terms."""
        return len(self.terms)

    def __contains__(self, source: str) -> bool:
        """Check if term exists (case-insensitive)."""
        return source.lower() in self.terms

    def __repr__(self) -> str:
        return f"GlossaryManager({len(self.terms)} terms, domains={self.domains_loaded})"


# Convenience function for quick glossary creation
def create_glossary(
    domains: list[str] | None = None,
    direction: str = "en-fr",
    custom_terms: dict[str, str] | None = None,
) -> GlossaryManager:
    """
    Create a glossary manager with specified domains.

    Args:
        domains: List of domains to load (e.g., ['ml', 'physics'])
        direction: Translation direction
        custom_terms: Additional custom terms to include

    Returns:
        Configured GlossaryManager

    Example:
        >>> glossary = create_glossary(['ml', 'physics'], custom_terms={'foo': 'bar'})
    """
    manager = GlossaryManager()

    if domains:
        for domain in domains:
            manager.load_domain(domain, direction)

    if custom_terms:
        manager.load_from_dict(custom_terms, domain="custom")

    return manager
