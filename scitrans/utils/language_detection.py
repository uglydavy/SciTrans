"""
Language Detection Utilities

Provides automatic language detection for source documents.
"""

from __future__ import annotations

import logging

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
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "bg": "Bulgarian",
    "hr": "Croatian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "el": "Greek",
    "tr": "Turkish",
    "he": "Hebrew",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "te": "Telugu",
    "ur": "Urdu",
}

# Language families for better detection
LANGUAGE_FAMILIES = {
    "latin": ["en", "fr", "es", "it", "pt", "ro"],
    "germanic": ["de", "nl", "sv", "da", "no"],
    "slavic": ["ru", "pl", "cs", "sk", "bg", "hr", "sl"],
    "asian": ["zh", "ja", "ko", "th", "vi", "hi", "bn", "ta", "te"],
    "semitic": ["ar", "he", "ur"],
    "other": ["el", "tr", "fi", "hu", "id", "ms"],
}


def detect_language(text: str, sample_size: int = 1000) -> str | None:
    """
    Detect language from text sample.

    Uses heuristics and character analysis for detection.
    For production, consider using langdetect or polyglot libraries.

    Args:
        text: Text to analyze
        sample_size: Maximum characters to analyze

    Returns:
        Language code (e.g., "en", "fr") or None if uncertain
    """
    if not text or len(text.strip()) < 10:
        return None

    # Sample text
    sample = text[:sample_size].lower()

    # Character-based detection
    char_counts = {}
    for char in sample:
        if char.isalpha():
            char_counts[char] = char_counts.get(char, 0) + 1

    # Common patterns
    patterns = {
        "en": ["the", "and", "is", "are", "was", "were"],
        "fr": ["le", "de", "et", "est", "les", "des"],
        "es": ["el", "la", "de", "que", "y", "en"],
        "de": ["der", "die", "das", "und", "ist", "sind"],
        "zh": ["的", "是", "在", "有", "和", "了"],
        "ja": ["の", "は", "に", "を", "が", "で"],
        "ar": ["ال", "في", "من", "على", "إلى", "أن"],
        "ru": ["и", "в", "не", "что", "на", "с"],
    }

    scores = {}
    for lang_code, common_words in patterns.items():
        score = sum(sample.count(word) for word in common_words)
        scores[lang_code] = score

    # Unicode range detection
    unicode_ranges = {
        "zh": (0x4E00, 0x9FFF),  # CJK Unified Ideographs
        "ja": (0x3040, 0x309F),  # Hiragana
        "ko": (0xAC00, 0xD7AF),  # Hangul
        "ar": (0x0600, 0x06FF),  # Arabic
        "he": (0x0590, 0x05FF),  # Hebrew
        "ru": (0x0400, 0x04FF),  # Cyrillic
        "el": (0x0370, 0x03FF),  # Greek
        "th": (0x0E00, 0x0E7F),  # Thai
    }

    for lang_code, (start, end) in unicode_ranges.items():
        count = sum(1 for char in sample if start <= ord(char) <= end)
        if count > len(sample) * 0.1:  # 10% threshold
            scores[lang_code] = scores.get(lang_code, 0) + count * 10

    if not scores:
        return None

    # Return language with highest score
    detected = max(scores.items(), key=lambda x: x[1])
    if detected[1] > 0:
        return detected[0]

    return None


def get_language_name(lang_code: str) -> str:
    """Get language name from code."""
    return SUPPORTED_LANGUAGES.get(lang_code, lang_code.upper())


def is_language_supported(lang_code: str) -> bool:
    """Check if language code is supported."""
    return lang_code in SUPPORTED_LANGUAGES


def get_all_supported_languages() -> list[tuple[str, str]]:
    """Get all supported languages as (name, code) tuples."""
    return [(name, code) for code, name in sorted(SUPPORTED_LANGUAGES.items())]
