from __future__ import annotations

import re
from dataclasses import dataclass

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
            MaskRule(
                "MATH_DISPLAY", re.compile(r"\$\$.*?\$\$|\\\[.*?\\\]", re.DOTALL), priority=80
            ),
            MaskRule(
                "MATH_INLINE", re.compile(r"\$(?!\$).*?\$|\\\(.*?\\\)", re.DOTALL), priority=70
            ),
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
        self, rules: list[MaskRule] | None = None, placeholder_fmt: str = DEFAULT_PLACEHOLDER_FMT
    ):
        self.rules = rules or default_rules()
        self.placeholder_fmt = placeholder_fmt

    def mask(self, text: str) -> tuple[str, dict[str, str], dict[str, int]]:
        registry: dict[str, str] = {}
        counts: dict[str, int] = {}

        masked = text
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

        # Exact restoration
        for ph, original in registry.items():
            if ph in out:
                out = out.replace(ph, original)
            else:
                errors.append(f"missing_placeholder:{ph}")

        if errors and tolerant:
            # Attempt very small repairs: sometimes models add spaces inside brackets.
            # Example: "<< MATH_INLINE_0001 >>"
            repaired = out
            for ph, original in registry.items():
                if ph in repaired:
                    continue

                ph_loose = re.escape(ph)
                ph_loose = ph_loose.replace("_", r"\s*_\s*")
                # allow whitespace inside the brackets
                ph_loose = ph_loose.replace("<<", r"<<\s*").replace(">>", r"\s*>>")
                candidate = re.compile(ph_loose)
                m = candidate.search(repaired)
                if m:
                    repaired = repaired[: m.start()] + original + repaired[m.end() :]
                    err = f"missing_placeholder:{ph}"
                    if err in errors:
                        errors.remove(err)

            out = repaired

        return out, errors

    @staticmethod
    def placeholders_present(text: str, registry: dict[str, str]) -> bool:
        return all(ph in text for ph in registry.keys())
