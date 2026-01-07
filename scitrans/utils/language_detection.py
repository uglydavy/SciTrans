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
    sample = text[:sample_size]

    # CRITICAL: Detect CJK (Chinese/Japanese/Korean) characters first
    # These use Unicode ranges that don't match Latin word patterns
    cjk_chars = 0
    total_chars = len(sample)
    
    for char in sample:
        code = ord(char)
        # Chinese (CJK Unified Ideographs)
        if 0x4E00 <= code <= 0x9FFF:
            cjk_chars += 1
        # Japanese Hiragana/Katakana
        elif 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
            cjk_chars += 1
        # Korean Hangul
        elif 0xAC00 <= code <= 0xD7AF:
            cjk_chars += 1
        # CJK Symbols and Punctuation
        elif 0x3000 <= code <= 0x303F:
            cjk_chars += 0.5  # Count punctuation as partial
    
    # If more than 30% CJK characters, likely CJK language
    if total_chars > 0 and cjk_chars / total_chars > 0.3:
        # Determine which CJK language based on character types
        chinese_chars = sum(1 for c in sample if 0x4E00 <= ord(c) <= 0x9FFF)
        japanese_chars = sum(1 for c in sample if (0x3040 <= ord(c) <= 0x309F or 0x30A0 <= ord(c) <= 0x30FF))
        korean_chars = sum(1 for c in sample if 0xAC00 <= ord(c) <= 0xD7AF)
        
        if chinese_chars > japanese_chars and chinese_chars > korean_chars:
            confidence = min(cjk_chars / total_chars * 1.5, 0.9)
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"M","location":"language_detection.py:95","message":"Detected Chinese text","data":{"cjk_ratio":cjk_chars/total_chars,"confidence":confidence,"sample_preview":sample[:50]}})+'\n')
            # #endregion
            return "zh", confidence
        elif japanese_chars > korean_chars:
            confidence = min(cjk_chars / total_chars * 1.5, 0.9)
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"M","location":"language_detection.py:103","message":"Detected Japanese text","data":{"cjk_ratio":cjk_chars/total_chars,"confidence":confidence,"sample_preview":sample[:50]}})+'\n')
            # #endregion
            return "ja", confidence
        elif korean_chars > 0:
            confidence = min(cjk_chars / total_chars * 1.5, 0.9)
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"M","location":"language_detection.py:111","message":"Detected Korean text","data":{"cjk_ratio":cjk_chars/total_chars,"confidence":confidence,"sample_preview":sample[:50]}})+'\n')
            # #endregion
            return "ko", confidence
        else:
            # Generic CJK (likely Chinese)
            confidence = min(cjk_chars / total_chars * 1.5, 0.9)
            # #region agent log
            with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                import json
                f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"M","location":"language_detection.py:119","message":"Detected generic CJK text","data":{"cjk_ratio":cjk_chars/total_chars,"confidence":confidence,"sample_preview":sample[:50]}})+'\n')
            # #endregion
            return "zh", confidence

    # For non-CJK text, use word-based detection
    sample_lower = sample.lower()
    words = re.findall(r"\b[a-zàáâãäåæçèéêëìíîïðñòóôõöøùúûüýþÿ]+\b", sample_lower)

    if not words:
        # No Latin words found - might be other script or symbols
        # Default to English with low confidence
        return "en", 0.1

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

    # #region agent log
    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
        import json
        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"M","location":"language_detection.py:155","message":"Detected language via word matching","data":{"lang_code":lang_code,"confidence":confidence,"sample_preview":sample[:50]}})+'\n')
    # #endregion

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

