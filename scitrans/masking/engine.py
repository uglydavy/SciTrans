from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from scitrans.core.models import Block
# Import placeholder helpers for generation and validation
from scitrans.masking.placeholders import generate_placeholder

logger = logging.getLogger(__name__)

# Placeholder generation is handled dynamically via scitrans.masking.placeholders.
# The old DEFAULT_PLACEHOLDER_FMT is kept for backwards compatibility but is no longer
# used to construct new placeholders. Instead, each placeholder embeds a CRC32 checksum
# of the original span. See scitrans.masking.placeholders.generate_placeholder for details.
DEFAULT_PLACEHOLDER_FMT = "@@SCITRANS_{kind}_{num:04d}_{crc:08X}@@"

# Common academic/technical terms that are NOT person names
# These patterns prevent false masking of section titles, technical terms, etc.
ACADEMIC_TERMS = {
    # Document structure
    "Abstract", "Summary", "Introduction", "Conclusion", "Results",
    "Methodology", "Discussion", "References", "Appendix", "Section",
    "Chapter", "Subsection", "Paragraph", "Document", "Report",
    "Background", "Overview", "Preface", "Acknowledgments", "Index",
    
    # Research terms (two-word combinations)
    "Content Analysis", "Data Analysis", "Statistical Analysis",
    "Computational Complexity", "Machine Learning", "Deep Learning",
    "Natural Language", "Artificial Intelligence", "Computer Vision",
    "Data Science", "Information Retrieval", "Pattern Recognition",
    "Computer Science", "Software Engineering", "Systems Engineering",
    "Distributed Systems", "Operating Systems", "Database Systems",
    
    # Technical phrases (common patterns)
    "System Architecture", "Network Protocol", "Database Management",
    "Software Engineering", "Hardware Implementation", "Algorithm Design",
    "Performance Evaluation", "Experimental Results", "Comparative Study",
    "Case Study", "Literature Review", "Systematic Review",
    "Related Work", "Future Work", "Empirical Study",
    
    # Method/content descriptors
    "Mathematical Content", "Theoretical Framework", "Empirical Evidence",
    "Quantitative Research", "Qualitative Research", "Mixed Methods",
    "Research Methodology", "Research Design", "Data Collection",
    "Data Visualization", "Result Summary", "Statistical Significance",
    
    # Table/figure related
    "Table Content", "Figure Caption", "Chart Data", "Graph Analysis",
    "Visual Analysis", "Image Processing", "Signal Processing",
    
    # Analysis types
    "Comparative Analysis", "Complexity Analysis", "Performance Analysis",
    "Error Analysis", "Risk Analysis", "Cost Analysis",
    "Sensitivity Analysis", "Trend Analysis", "Gap Analysis",
    
    # Common single words that appear in technical contexts
    "Analysis", "Content", "Method", "Approach", "Framework", "Model",
    "Structure", "Process", "System", "Network", "Protocol", "Interface",
    "Architecture", "Implementation", "Evaluation", "Comparison",
    "Validation", "Verification", "Optimization", "Enhancement",
    
    # Field-specific terms
    "Neural Network", "Decision Tree", "Support Vector",
    "Random Forest", "Gradient Descent", "Feature Engineering",
    "Cross Validation", "Dimensionality Reduction", "Anomaly Detection",
    "Sentiment Analysis", "Topic Modeling", "Named Entity",
    
    # Common technical adjective + noun combinations
    "Experimental Setup", "Proposed Method", "Baseline Method",
    "Novel Approach", "Existing Methods", "Current State",
    "Previous Work", "Recent Advances", "Key Findings",
    "Main Contributions", "Future Directions", "Open Problems",
}

# Additional technical keywords that often appear in false positive matches
TECHNICAL_KEYWORDS = {
    "Analysis", "Content", "Data", "System", "Method",
    "Network", "Protocol", "Framework", "Model", "Structure",
    "Process", "Algorithm", "Design", "Implementation", "Evaluation",
    "Performance", "Complexity", "Architecture", "Engineering",
    "Science", "Research", "Study", "Review", "Survey",
}


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
            # Excludes common document structure words
            # Also matches names with ID numbers: "Name / ID: 123456"
            # CRITICAL: Use negative lookahead to exclude document words
            MaskRule("PERSON_NAME", re.compile(r"\b(?!(?:Small|Test|Document|Report|Study|Section|Chapter|Introduction|Conclusion|Results|Methodology|Abstract|Summary)\b)(?:[A-Z][a-z]{2,}(?:\s+[A-Z]\.)?\s+){1,2}[A-Z][a-z]{2,}(?:\s*/\s*ID\s*:\s*\d+)?\b"), priority=68),
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

    def is_likely_person_name(self, text: str, block: Optional[Block] = None) -> bool:
        """Validate if text is likely a person name vs technical term.
        
        This method uses multiple heuristics to avoid false positives:
        1. Exact match against academic terms list
        2. Check for technical keywords in the text
        3. Block metadata (headers, titles)
        4. Text formatting (all caps, special patterns)
        5. Linguistic patterns typical of person names
        
        Args:
            text: The matched text to validate
            block: Optional block context for additional validation
            
        Returns:
            True if text is likely a person name, False otherwise
        """
        # Exact match against academic terms (case-sensitive)
        if text in ACADEMIC_TERMS:
            return False
        
        # Case-insensitive check for multi-word academic terms
        text_lower = text.lower()
        for term in ACADEMIC_TERMS:
            if text_lower == term.lower():
                return False
        
        # Check each word against technical keywords
        words = text.split()
        for word in words:
            if word in TECHNICAL_KEYWORDS:
                return False
            # Also check case-insensitive
            if word.lower().capitalize() in TECHNICAL_KEYWORDS:
                return False
        
        # Exclude if block is a header/title
        if block and (block.meta.get("is_header") or 
                      block.meta.get("block_type") in ("title", "header", "subheader")):
            return False
        
        # Exclude if all caps (likely acronym or section header)
        if text.isupper() and len(text) > 3:  # Allow short all-caps like "PhD"
            return False
        
        # Exclude common section title patterns
        if any(keyword in text for keyword in [
            "Section", "Chapter", "Part", "Figure", "Table",
            "Appendix", "Introduction", "Conclusion", "Results"
        ]):
            return False
        
        # Exclude if it ends with common technical suffixes
        if any(text.endswith(suffix) for suffix in [
            "Analysis", "Framework", "System", "Method", "Approach",
            "Model", "Structure", "Algorithm", "Design", "Process"
        ]):
            return False
        
        # Valid person names typically have:
        # - 2-4 words (first name, optional middle, last name)
        # - Each word properly capitalized (not all caps)
        # - Reasonable length (not too short or too long)
        word_count = len(words)
        if word_count < 2 or word_count > 4:
            return False
        
        # Check if words follow proper name capitalization
        # (First letter capital, rest lowercase, except middle initials)
        for word in words:
            # Allow middle initials like "J." or "T."
            if len(word) == 2 and word[1] == '.':
                continue
            # Check standard capitalization
            if not (word[0].isupper() and (len(word) == 1 or word[1:].islower() or word[1:].istitle())):
                return False
        
        # If we've passed all exclusion checks, it's likely a person name
        return True

    def mask(
        self, 
        text: str, 
        block: Optional[Block] = None
    ) -> tuple[str, dict[str, str], dict[str, int]]:
        registry: dict[str, str] = {}
        counts: dict[str, int] = {}

        masked = text
        
        # Track rejected masks for debugging
        rejected_masks: list[tuple[str, str]] = []
        
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
                matched_text = m.group(0)
                
                # Validate PERSON_NAME matches to avoid false positives
                if rule.kind == "PERSON_NAME":
                    if not self.is_likely_person_name(matched_text, block):
                        rejected_masks.append((rule.kind, matched_text))
                        return matched_text  # Don't mask - return original text
                
                n += 1
                placeholder = generate_placeholder(rule.kind, n, matched_text)
                registry[placeholder] = matched_text
                return placeholder

            masked = rule.pattern.sub(_repl, masked)
            if n:
                counts[rule.kind] = n

        # Log rejected masks (only in debug mode to avoid noise)
        if rejected_masks and block:
            logger.debug(
                f"Block {block.id}: Rejected {len(rejected_masks)} false positive mask(s): "
                f"{rejected_masks[:5]}{'...' if len(rejected_masks) > 5 else ''}"
            )

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
        
        # CRITICAL: Validate all placeholders were restored
        remaining_placeholders = re.findall(r'@@SCITRANS_\w+_\d+_[A-F0-9]+@@', out)
        if remaining_placeholders:
            for ph in remaining_placeholders:
                # Check if this placeholder is in the registry
                if ph in registry:
                    # Placeholder was in registry but didn't get restored - force restore now
                    out = out.replace(ph, registry[ph])
                    logger.warning(f"Force-restored placeholder: {ph}")
                else:
                    # Placeholder not in registry - remove it (likely hallucination)
                    logger.error(f"Unrestore-able placeholder found (not in registry): {ph} - REMOVING")
                    out = out.replace(ph, "")  # Remove hallucinated placeholder
                    errors.append(f"hallucinated_placeholder:{ph}")
        
        # Log restoration errors at appropriate level
        if errors:
            logger.error(f"Placeholder restoration errors: {len(errors)} errors - {errors[:5]}")

        return out, errors

    @staticmethod
    def placeholders_present(text: str, registry: dict[str, str]) -> bool:
        return all(ph in text for ph in registry.keys())
