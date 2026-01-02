"""
Language Detection Utilities

Provides automatic language detection for source documents.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Extended language support
SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
    "ar": "Arabic",
    "nl": "Dutch",
    "sv": "Swedish",
    "pl": "Polish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "th": "Thai",
    "hi": "Hindi",
}

# Common words for language detection (simple heuristic)
LANGUAGE_INDICATORS = {
    "en": {
        "common": ["the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"],
        "articles": ["the", "a", "an"],
    },
    "fr": {
        "common": ["le", "de", "et", "à", "un", "il", "être", "et", "en", "avoir", "que", "pour"],
        "articles": ["le", "la", "les", "un", "une", "des"],
    },
    "es": {
        "common": ["el", "la", "de", "que", "y", "a", "en", "un", "ser", "se", "no", "haber"],
        "articles": ["el", "la", "los", "las", "un", "una", "unos", "unas"],
    },
    "de": {
        "common": ["der", "die", "und", "in", "den", "von", "zu", "das", "mit", "sich", "des", "auf"],
        "articles": ["der", "die", "das", "ein", "eine"],
    },
}


def detect_language(text: str, sample_size: int = 500) -> tuple[str, float]:
    """
    Detect the language of text using simple heuristics.

    Args:
        text: Text to analyze
        sample_size: Maximum characters to analyze (for performance)

    Returns:
        Tuple of (language_code, confidence) where confidence is 0.0-1.0
    """
    if not text or not text.strip():
        return "en", 0.0  # Default to English

    # Take a sample for performance
    sample = text[:sample_size].lower()

    # Extract words (simple tokenization)
    words = re.findall(r"\b[a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+\b", sample)

    if not words:
        return "en", 0.0

    # Count matches for each language
    scores: dict[str, float] = {}

    for lang_code, indicators in LANGUAGE_INDICATORS.items():
        score = 0.0
        total_words = len(words)

        if total_words == 0:
            continue

        # Check common words
        common_matches = sum(1 for word in words if word in indicators["common"])
        article_matches = sum(1 for word in words if word in indicators["articles"])

        # Weight articles more heavily (they're more distinctive)
        score = (common_matches * 0.5 + article_matches * 2.0) / total_words
        scores[lang_code] = score

    if not scores:
        return "en", 0.0

    # Find best match
    best_lang = max(scores.items(), key=lambda x: x[1])
    lang_code, confidence = best_lang

    # Normalize confidence (heuristic-based, so cap at 0.8)
    confidence = min(confidence * 1.5, 0.8)

    logger.debug(f"Language detection: {lang_code} (confidence: {confidence:.2f})")

    return lang_code, confidence


def detect_language_from_pdf(
    text_blocks: list[str], min_confidence: float = 0.3
) -> tuple[str, float]:
    """
    Detect language from multiple text blocks (e.g., from a PDF).

    Args:
        text_blocks: List of text blocks from the document
        min_confidence: Minimum confidence to return a detection

    Returns:
        Tuple of (language_code, confidence)
    """
    if not text_blocks:
        return "en", 0.0

    # Combine blocks (up to reasonable limit)
    combined_text = " ".join(text_blocks[:20])  # Use first 20 blocks

    lang_code, confidence = detect_language(combined_text)

    if confidence < min_confidence:
        logger.warning(
            f"Language detection confidence ({confidence:.2f}) below threshold ({min_confidence}). "
            f"Defaulting to English."
        )
        return "en", 0.0

    return lang_code, confidence


def is_language_code_valid(code: str) -> bool:
    """Check if a language code is supported."""
    return code.lower() in SUPPORTED_LANGUAGES


def get_language_name(code: str) -> str:
    """Get the full name of a language from its code."""
    return SUPPORTED_LANGUAGES.get(code.lower(), code.upper())

