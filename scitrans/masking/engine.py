from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from scitrans.core.models import Block

# ASCII placeholders are more stable across models/fonts than Unicode ⟦⟧
DEFAULT_PLACEHOLDER_FMT = "<<{kind}_{num:04d}>>"


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
        
        # Use advanced math detection if available and block is provided
        if self.use_advanced_math and self.advanced_math and block:
            # First, mask math using span-level analysis (catches math without delimiters)
            # The advanced math detector uses {num} format, so we construct it from our format
            # Our format is "<<{kind}_{num:04d}>>", so we replace {kind} with "MATH" and keep {num:04d}
            if "{kind}" in self.placeholder_fmt:
                # Format has {kind} placeholder - replace it with "MATH"
                math_placeholder_fmt = self.placeholder_fmt.replace("{kind}", "MATH")
            else:
                # Format doesn't have {kind} - construct it manually
                # Extract the base format (e.g., "<<{num:04d}>>") and add "MATH_"
                base_fmt = self.placeholder_fmt
                if base_fmt.startswith("<<") and base_fmt.endswith(">>"):
                    inner = base_fmt[2:-2]  # Remove << and >>
                    if "{num" in inner:
                        # Replace {num:04d} with MATH_{num:04d}
                        math_placeholder_fmt = f"<<MATH_{inner}>>"
                    else:
                        math_placeholder_fmt = f"<<MATH_{inner}>>"
                else:
                    # Fallback: use default format
                    math_placeholder_fmt = "<<MATH_{num:04d}>>"
            
            math_masked, math_registry = self.advanced_math.mask_math_in_text(
                masked, block, placeholder_fmt=math_placeholder_fmt
            )
            masked = math_masked
            registry.update(math_registry)
            if math_registry:
                counts["MATH_ADVANCED"] = len(math_registry)

        # Apply standard regex-based rules (for code, URLs, etc.)
        for rule in self.rules:
            n = 0

            def _repl(m: re.Match, rule=rule) -> str:
                nonlocal n
                n += 1
                placeholder = self.placeholder_fmt.format(kind=rule.kind, num=n)
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

        # Exact restoration - try both <<>> and ⟦⟧ formats
        for ph, original in registry.items():
            if ph in out:
                out = out.replace(ph, original)
            else:
                # Try alternative format: if we have <<MATH_INLINE_0001>>, also try ⟦MATH_INLINE_0001⟧
                # Extract the kind and number from placeholder
                ph_alt = None
                if ph.startswith("<<") and ph.endswith(">>"):
                    # Convert <<KIND_NUM>> to ⟦KIND_NUM⟧
                    inner = ph[2:-2]  # Remove << and >>
                    ph_alt = f"⟦{inner}⟧"
                elif ph.startswith("⟦") and ph.endswith("⟧"):
                    # Convert ⟦KIND_NUM⟧ to <<KIND_NUM>>
                    inner = ph[1:-1]  # Remove ⟦ and ⟧
                    ph_alt = f"<<{inner}>>"
                
                if ph_alt and ph_alt in out:
                    out = out.replace(ph_alt, original)
                else:
                    errors.append(f"missing_placeholder:{ph}")

        if errors and tolerant:
            # Attempt very small repairs: sometimes models add spaces inside brackets.
            # Example: "<< MATH_INLINE_0001 >>" or "⟦ MATH_INLINE_0001 ⟧"
            repaired = out
            for ph, original in registry.items():
                if ph in repaired:
                    continue

                # Try both formats with loose matching
                for fmt in [ph, ph.replace("<<", "⟦").replace(">>", "⟧")]:
                    if fmt in repaired:
                        continue
                    
                    ph_loose = re.escape(fmt)
                    ph_loose = ph_loose.replace("_", r"\s*_\s*")
                    # allow whitespace inside the brackets (both formats)
                    ph_loose = ph_loose.replace("<<", r"<<\s*").replace(">>", r"\s*>>")
                    ph_loose = ph_loose.replace("⟦", r"⟦\s*").replace("⟧", r"\s*⟧")
                    candidate = re.compile(ph_loose)
                    m = candidate.search(repaired)
                    if m:
                        repaired = repaired[: m.start()] + original + repaired[m.end() :]
                        err = f"missing_placeholder:{ph}"
                        if err in errors:
                            errors.remove(err)
                        break

            out = repaired

        return out, errors

    @staticmethod
    def placeholders_present(text: str, registry: dict[str, str]) -> bool:
        return all(ph in text for ph in registry.keys())
