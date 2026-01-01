"""
Translation Memory System

Stores and retrieves previous translations for reuse.
Supports fuzzy matching for similar blocks.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


class TranslationMemory:
    """
    Translation memory for storing and retrieving previous translations.

    Features:
    - Exact match lookup
    - Fuzzy match for similar blocks
    - Confidence scoring
    - Persistent storage
    """

    def __init__(self, memory_file: str | Path = "translation_memory.json"):
        self.memory_file = Path(memory_file)
        self.memory: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        """Load translation memory from file."""
        if self.memory_file.exists():
            try:
                content = self.memory_file.read_text(encoding="utf-8")
                self.memory = json.loads(content)
                logger.info(f"Loaded {len(self.memory)} translation pairs from memory")
            except Exception as e:
                logger.warning(f"Failed to load translation memory: {e}")
                self.memory = {}
        else:
            self.memory = {}

    def save(self) -> None:
        """Save translation memory to file."""
        try:
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(
                json.dumps(self.memory, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.debug(f"Saved {len(self.memory)} translation pairs to memory")
        except Exception as e:
            logger.error(f"Failed to save translation memory: {e}")

    def add(
        self,
        source: str,
        target: str,
        source_lang: str,
        target_lang: str,
        metadata: dict | None = None,
    ) -> None:
        """
        Add a translation pair to memory.

        Args:
            source: Source text
            target: Translated text
            source_lang: Source language code
            target_lang: Target language code
            metadata: Optional metadata (backend, quality score, etc.)
        """
        key = self._make_key(source, source_lang, target_lang)
        self.memory[key] = {
            "source": source,
            "target": target,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "metadata": metadata or {},
        }
        self.save()

    def get(
        self, source: str, source_lang: str, target_lang: str, min_confidence: float = 0.95
    ) -> str | None:
        """
        Get exact translation from memory.

        Args:
            source: Source text
            source_lang: Source language code
            target_lang: Target language code
            min_confidence: Minimum confidence (not used for exact match)

        Returns:
            Translated text if found, None otherwise
        """
        key = self._make_key(source, source_lang, target_lang)
        entry = self.memory.get(key)
        if entry:
            return entry["target"]
        return None

    def fuzzy_search(
        self,
        source: str,
        source_lang: str,
        target_lang: str,
        min_similarity: float = 0.85,
        top_k: int = 1,
    ) -> list[tuple[str, float]]:
        """
        Find similar translations using fuzzy matching.

        Args:
            source: Source text to match
            source_lang: Source language code
            target_lang: Target language code
            min_similarity: Minimum similarity score (0.0-1.0)
            top_k: Number of top matches to return

        Returns:
            List of (translated_text, similarity_score) tuples
        """
        lang_key = f"{source_lang}-{target_lang}"
        candidates = []

        for key, entry in self.memory.items():
            if not key.startswith(lang_key):
                continue

            similarity = fuzz.ratio(source, entry["source"]) / 100.0

            if similarity >= min_similarity:
                candidates.append((entry["target"], similarity))

        # Sort by similarity (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)

        return candidates[:top_k]

    def _make_key(self, source: str, source_lang: str, target_lang: str) -> str:
        """Create a key for translation memory lookup."""
        lang_key = f"{source_lang}-{target_lang}"
        # Use hash for long texts, full text for short ones
        if len(source) > 100:
            import hashlib

            source_hash = hashlib.md5(source.encode()).hexdigest()
            return f"{lang_key}:{source_hash}"
        else:
            return f"{lang_key}:{source}"

    def clear(self) -> None:
        """Clear all translation memory."""
        self.memory = {}
        self.save()
        logger.info("Translation memory cleared")

    def stats(self) -> dict:
        """Get statistics about translation memory."""
        lang_pairs = {}
        for key in self.memory.keys():
            lang_pair = key.split(":")[0] if ":" in key else "unknown"
            lang_pairs[lang_pair] = lang_pairs.get(lang_pair, 0) + 1

        return {
            "total_pairs": len(self.memory),
            "language_pairs": lang_pairs,
        }
