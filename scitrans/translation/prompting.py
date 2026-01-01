from __future__ import annotations


def build_system_prompt(*, source: str, target: str, glossary: dict[str, str] | None = None) -> str:
    lines = [
        "You are a professional translator specializing in scientific and technical documents.",
        f"Translate from {source} to {target}.",
        "",
        "CRITICAL OUTPUT RULES:",
        "- Output ONLY the translated text (no labels, no explanations).",
        "- Preserve ALL placeholders EXACTLY (e.g., ⟦MATH_INLINE_0001⟧).",
        "- Do NOT translate LaTeX/math inside placeholders.",
        "- Preserve numbers, units, and citations.",
        "- Preserve bullet structure and line breaks as much as possible.",
    ]
    if glossary:
        lines += ["", "GLOSSARY (must follow exactly):"]
        for k, v in glossary.items():
            lines.append(f"- {k} -> {v}")
    return "\n".join(lines)
