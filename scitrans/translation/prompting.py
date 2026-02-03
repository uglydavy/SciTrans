from __future__ import annotations

from typing import Iterable

PROMPT_VERSION = "v3.1"


def _select_glossary_terms(
    glossary: dict[str, str] | None,
    source_text: str | None,
    max_terms: int = 25,
) -> list[tuple[str, str]]:
    if not glossary:
        return []
    if not source_text:
        return list(glossary.items())[:max_terms]
    source_lower = source_text.lower()
    selected = []
    for k, v in glossary.items():
        if k.lower() in source_lower:
            selected.append((k, v))
    # Prefer longer terms first
    selected.sort(key=lambda kv: len(kv[0]), reverse=True)
    return selected[:max_terms]


def build_system_prompt(
    *,
    source: str,
    target: str,
    glossary: dict[str, str] | None = None,
    source_text: str | None = None,
    is_header: bool = False,
    is_bullet: bool = False,
    is_table: bool = False,
) -> str:
    """Build a concise, strict system prompt for translation."""
    lines: list[str] = [
        "You are a professional translator for scientific and technical documents.",
        f"Translate from {source.upper()} to {target.upper()}.",
        "Output ONLY the translated text. No labels, no explanations.",
        "",
        "Core rules:",
        "- Translate all visible text (including headers, captions, and TOC entries).",
        "- Preserve numbers, units, citations, and punctuation.",
        "- Keep formatting: line breaks, bullets, and numbering structure.",
        "- Do not add or remove content; no greetings or commentary.",
        "",
        "Placeholder rules (MANDATORY):",
        "- Preserve placeholders EXACTLY as written.",
        "- Common formats: @@SCITRANS_KIND_0001_ABCD1234@@, <<KIND_0001>>, ⟦KIND_0001⟧.",
        "- Do NOT modify, translate, remove, or create placeholders.",
        "- If the input is ONLY a placeholder, output it unchanged.",
        "",
        "Never add extra tokens or labels. Translate only what is given.",
    ]

    if is_header:
        lines += [
            "",
            "Header/title rules:",
            "- Keep section numbers and prefixes (e.g., '1.', 'Section 2:', 'Chapter 3:').",
            "- Translate the words, keep numbers and punctuation.",
            "- Keep it concise; one line only.",
        ]

    if is_bullet:
        lines += [
            "",
            "Bullet rules:",
            "- Keep the bullet symbol (•, -, *, ·) and indentation.",
            "- Translate the text after the bullet.",
        ]

    if is_table:
        lines += [
            "",
            "Table rules:",
            "- Preserve column separators (|, tabs, multi-spaces).",
            "- Keep row structure and alignment; translate cell text only.",
        ]

    selected_terms = _select_glossary_terms(glossary, source_text)
    if selected_terms:
        lines += ["", "Glossary (use these exact translations):"]
        for k, v in selected_terms:
            lines.append(f"- {k} -> {v}")

    return "\n".join(lines)


def get_prompt_version() -> str:
    return PROMPT_VERSION
