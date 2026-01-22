"""Identity translation detection (pipeline compatibility)."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import List


@dataclass
class IdentityCheckResult:
    is_identity: bool
    confidence: float = 0.0
    reason: str = ""
    valid_identical_content: List[str] = field(default_factory=list)
    should_retry: bool = False


def _norm(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def check_identity_translation(
    source_text: str,
    translated_text: str,
    *,
    is_header: bool = False,
    is_bullet: bool = False,
    is_title: bool = False,
    block_type: str = "normal",
    **_: object,
) -> IdentityCheckResult:
    if translated_text is None:
        translated_text = ""
    if not isinstance(translated_text, str):
        translated_text = str(translated_text)

    src = source_text or ""
    tgt = translated_text

    if not tgt.strip():
        return IdentityCheckResult(
            is_identity=True,
            confidence=1.0,
            reason="Empty translation",
            valid_identical_content=[],
            should_retry=True,
        )

    src_n = _norm(src)
    tgt_n = _norm(tgt)

    if src_n and src_n == tgt_n:
        # allow identity for pure punctuation/numerics
        if re.fullmatch(r"[\W\d\s]+", src or ""):
            return IdentityCheckResult(
                is_identity=False,
                confidence=1.0,
                reason="Numeric/punctuation-only; identity allowed",
                valid_identical_content=[tgt],
                should_retry=False,
            )
        
        # NEW: Check for technical terms / proper nouns
        try:
            from scitrans.utils.content_detector import contains_whitelisted_terms
            if contains_whitelisted_terms(src) or contains_whitelisted_terms(tgt):
                # Technical terms - allow identity (e.g., "GPT-3", "DALL-E", "RLHF")
                return IdentityCheckResult(
                    is_identity=False,  # Not identity - it's valid
                    confidence=0.0,
                    reason="Contains technical terms - identity allowed",
                    valid_identical_content=[tgt],
                    should_retry=False,
                )
        except ImportError:
            pass  # Fall through if content_detector not available
        
        # NEW: Check for proper nouns (capitalized words, likely names/places)
        src_words = [w for w in src.split() if w]
        tgt_words = [w for w in tgt.split() if w]
        if len(src_words) <= 3 and len(tgt_words) <= 3:
            # Short phrase - check if all words are capitalized (likely proper noun)
            if all(w and w[0].isupper() for w in src_words) and all(w and w[0].isupper() for w in tgt_words):
                # Likely proper noun - allow identity
                return IdentityCheckResult(
                    is_identity=False,
                    confidence=0.0,
                    reason="Proper noun - identity allowed",
                    valid_identical_content=[tgt],
                    should_retry=False,
                )
        
        # NEW: Check for short common phrases that are valid in both languages
        # (e.g., "OK", "Yes", "No", "Hello", "Hi")
        common_phrases = {"ok", "yes", "no", "hello", "hi", "bye", "thanks", "thank you"}
        if src_n in common_phrases or tgt_n in common_phrases:
            return IdentityCheckResult(
                is_identity=False,
                confidence=0.0,
                reason="Common phrase - identity allowed",
                valid_identical_content=[tgt],
                should_retry=False,
            )

        # retry headers/titles more aggressively
        must_retry = bool(is_header or is_title or block_type in ("title", "header"))
        return IdentityCheckResult(
            is_identity=True,
            confidence=1.0,
            reason="Translation identical to source",
            valid_identical_content=[tgt],
            should_retry=must_retry,
        )

    return IdentityCheckResult(
        is_identity=False,
        confidence=0.0,
        reason="Not identity",
        valid_identical_content=[],
        should_retry=False,
    )


detect_identity_translation = check_identity_translation


class IdentityTranslationDetector:
    def check(self, source_text: str, translated_text: str, *, is_header: bool = False, **kwargs) -> IdentityCheckResult:
        return check_identity_translation(source_text, translated_text, is_header=is_header, **kwargs)
