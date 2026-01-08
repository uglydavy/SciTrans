from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from scitrans.core.models import Block
# Import placeholder helpers for generation and validation
from scitrans.masking.placeholders import generate_placeholder, validate_placeholders

# Placeholder generation is handled dynamically via scitrans.masking.placeholders.
# The old DEFAULT_PLACEHOLDER_FMT is kept for backwards compatibility but is no longer
# used to construct new placeholders. Instead, each placeholder embeds a CRC32 checksum
# of the original span. See scitrans.masking.placeholders.generate_placeholder for details.
DEFAULT_PLACEHOLDER_FMT = "@@SCITRANS_{kind}_{num:04d}_{crc:08X}@@"


@dataclass(frozen=True)
class MaskRule:
    kind: str
    pattern: re.Pattern
    priority: int = 0


def default_rules() -> list[MaskRule]:
    # Order matters: higher priority applies first
    return sorted(
        [
            MaskRule("CODEBLOCK", re.compile(r"```.*?```", re.DOTALL), priority=100),
            MaskRule("INLINECODE", re.compile(r"`[^`\n]+`"), priority=90),
            # LaTeX-ish math regions in *text* PDFs
            # Display math: $$...$$ or \[...\]
            MaskRule(
                "MATH_DISPLAY", re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL), priority=80
            ),
            # Inline math: $...$ (flexible - allows single chars like $x$)
            # Also matches \(...\) for LaTeX inline math
            MaskRule(
                "MATH_INLINE", re.compile(r"\$(?!\$)([^$\n]*?)\$|\\\(.*?\\\)", re.DOTALL), priority=70
            ),
            # Person names (more specific patterns to avoid false positives)
            # Matches: "John Smith", "Tchienkoua Franck Davy", "Ouedraogo T. Rachid Hérlot"
            # Pattern: 2-4 capitalized words, optionally with middle initial
            # Excludes common words that start with capital (like "The", "This", etc.)
            # Also matches names with ID numbers: "Name / ID: 123456"
            MaskRule("PERSON_NAME", re.compile(r"\b(?:[A-Z][a-z]{2,}(?:\s+[A-Z]\.)?\s+){1,2}[A-Z][a-z]{2,}(?:\s*/\s*ID\s*:\s*\d+)?\b"), priority=68),
            # Place names (capitalized, often with common place suffixes)
            MaskRule("PLACE_NAME", re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:City|State|Country|University|Institute|Laboratory|Center|Centre|Hospital|School|College))\b"), priority=67),
            # Table of contents entries (numbered sections)
            MaskRule("TOC_ENTRY", re.compile(r"^\s*\d+\.\d*(?:\s+\d+\.\d*)*\s+[A-Z].*$", re.MULTILINE), priority=66),
            # Figure/Table captions
            MaskRule("FIGURE_CAPTION", re.compile(r"\b(?:Figure|Fig\.|Table|Tab\.)\s+\d+[:\s]+.*", re.IGNORECASE), priority=65),
            # Bullet points - preserve exactly (CRITICAL for perfect rendering)
            MaskRule("BULLET", re.compile(r"^([•\-\*·▪▫])\s+", re.MULTILINE), priority=65),
            # URLs & emails
            MaskRule("URL", re.compile(r"(https?://|www\.)\S+"), priority=60),
            MaskRule("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), priority=50),
            # Citations like [12] or [3,4]
            MaskRule("CIT", re.compile(r"\[[0-9,\s]{1,20}\]"), priority=40),
        ],
        key=lambda r: (-r.priority, r.kind),
    )


class MaskingEngine:
    """Mask sensitive substrings to prevent LLM corruption.

    Strategy:
      1) Replace matches by robust placeholders `⟦KIND_0001⟧`.
      2) Store `placeholder -> original`.
      3) After translation, restore placeholders.
      4) Validate: all placeholders must be present.

    Repair policy:
      - If placeholders are missing, we can do tolerant matching or force re-translation
        (implemented at pipeline level).
    """

    def __init__(
        self, 
        rules: list[MaskRule] | None = None, 
        placeholder_fmt: str = DEFAULT_PLACEHOLDER_FMT,
        use_advanced_math: bool = True,
    ):
        self.rules = rules or default_rules()
        self.placeholder_fmt = placeholder_fmt
        self.use_advanced_math = use_advanced_math
        if use_advanced_math:
            try:
                from scitrans.masking.advanced_math_detector import AdvancedMathDetector
                self.advanced_math = AdvancedMathDetector()
            except ImportError:
                self.advanced_math = None
                self.use_advanced_math = False
        else:
            self.advanced_math = None

    def mask(
        self, 
        text: str, 
        block: Optional[Block] = None
    ) -> tuple[str, dict[str, str], dict[str, int]]:
        registry: dict[str, str] = {}
        counts: dict[str, int] = {}

        masked = text
        
        # Use advanced math detection if available and block is provided.  This masks
        # spans that are likely mathematical expressions even if they are not
        # delimited by $...$ or \(...\). The detector returns both the masked
        # text and a registry mapping its internal placeholders to original text.
        if self.use_advanced_math and self.advanced_math and block:
            math_masked, math_registry = self.advanced_math.mask_math_in_text(
                masked, block, placeholder_fmt=self.placeholder_fmt
            )
            masked = math_masked
            registry.update(math_registry)
            if math_registry:
                counts["MATH_ADVANCED"] = len(math_registry)

        # Apply standard regex-based rules (for code, URLs, etc.)
        for rule in self.rules:
            # Reset numbering per rule to maintain per-rule numbering
            n = 0

            def _repl(m: re.Match, rule=rule) -> str:
                nonlocal n
                n += 1
                placeholder = generate_placeholder(rule.kind, n, m.group(0))
                registry[placeholder] = m.group(0)
                return placeholder

            masked = rule.pattern.sub(_repl, masked)
            if n:
                counts[rule.kind] = n

        return masked, registry, counts

    def restore(
        self, translated: str, registry: dict[str, str], *, tolerant: bool = True
    ) -> tuple[str, list[str]]:
        errors: list[str] = []
        out = translated

        # Exact restoration – replace placeholder tokens directly where present
        for ph, original in registry.items():
            if ph in out:
                out = out.replace(ph, original)
            else:
                # Attempt loose matching: allow optional whitespace between token parts
                ph_esc = re.escape(ph)
                ph_pat = ph_esc.replace("_", r"\s*_\s*")
                ph_pat = ph_pat.replace("@@", r"@@\s*")
                m = re.search(ph_pat, out, re.IGNORECASE)
                if m:
                    out = out[: m.start()] + original + out[m.end():]
                else:
                    errors.append(f"missing_placeholder:{ph}")

        if errors and tolerant:
            # Attempt minor repairs: tokens sometimes get split by whitespace or partially removed
            repaired = out
            for ph, original in registry.items():
                if ph in repaired:
                    continue
                parts = ph.split("_")
                pat = re.escape(parts[0])
                for part in parts[1:]:
                    pat += r"\s*_\s*" + re.escape(part)
                m = re.search(pat, repaired, re.IGNORECASE)
                if m:
                    repaired = repaired[: m.start()] + original + repaired[m.end():]
                    err = f"missing_placeholder:{ph}"
                    if err in errors:
                        errors.remove(err)
            out = repaired

        return out, errors

    @staticmethod
    def placeholders_present(text: str, registry: dict[str, str]) -> bool:
        return all(ph in text for ph in registry.keys())
