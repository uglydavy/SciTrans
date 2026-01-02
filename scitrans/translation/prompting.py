from __future__ import annotations


def build_system_prompt(*, source: str, target: str, glossary: dict[str, str] | None = None, is_header: bool = False, is_bullet: bool = False) -> str:
    """Build system prompt with enhanced instructions for headers/titles/bullets.
    
    Args:
        source: Source language code
        target: Target language code
        glossary: Optional glossary dict
        is_header: True if this is a header/title block
        is_bullet: True if this is a bullet point
    """
    lines = [
        "You are a professional translator specializing in scientific and technical documents.",
        f"Your task: Translate text from {source.upper()} to {target.upper()}.",
        "",
        "CRITICAL INSTRUCTIONS:",
        f"1. You MUST translate the text from {source.upper()} to {target.upper()}.",
        "2. You MUST NOT return the source text unchanged - always translate it.",
        "3. You MUST NOT return generic responses, greetings, or explanations - ONLY the translated text.",
        "4. Output ONLY the translated text (no labels, no explanations, no source text, no greetings).",
        "5. Preserve ALL placeholders EXACTLY as written (e.g., ⟦MATH_INLINE_0001⟧).",
        "6. Do NOT translate LaTeX/math inside placeholders - keep them unchanged.",
        "7. Preserve numbers, units, and citations exactly.",
        "8. Preserve formatting:",
        "   - If source has bullets (•, -, *), preserve them in translation",
        "   - If source has NO bullets, do NOT add bullets to paragraphs",
        "   - Preserve section headers (e.g., '1. Introduction' → '1. Introduction' in target language)",
        "   - Preserve numbering EXACTLY:",
        "     * Section numbers: '1. ', '2)', 'Section 3:' must keep the number",
        "     * List numbers: '1.', '2.', '3.' must be preserved",
        "     * Page numbers and references: keep all numbers unchanged",
        "   - Numbering format: 'Section 2:' → 'Section 2 :' or 'Section 2:' (preserve colon/format)",
        "9. Translate ALL text including headers, titles, and section numbers.",
    ]
    
    # Enhanced instructions for headers/titles
    if is_header:
        lines.extend([
            "",
            "SPECIAL INSTRUCTIONS FOR HEADERS/TITLES:",
            "- This is a HEADER or TITLE block - it MUST be translated.",
            "- Even if the word exists in both languages (e.g., 'Introduction', 'Conclusion'),",
            "  you MUST provide the proper translation in the target language.",
            "- For section headers like 'Section 1:', translate 'Section' but keep the number.",
            "- Examples:",
            f"  * 'Introduction' → '{'Introduction' if target == 'en' else 'Introduction'}' (translate to target language)",
            f"  * 'Section 1' → '{'Section 1' if target == 'en' else 'Section 1'}' (translate 'Section', keep number)",
            f"  * 'Conclusion' → '{'Conclusion' if target == 'en' else 'Conclusion'}' (translate to target language)",
            "- DO NOT return the source text unchanged - always provide a translation.",
        ])
    
    # Enhanced instructions for bullet points
    if is_bullet:
        lines.extend([
            "",
            "SPECIAL INSTRUCTIONS FOR BULLET POINTS:",
            "- This is a BULLET POINT - it MUST be translated.",
            "- Preserve the bullet character (•, -, *) but translate the text.",
            "- Examples:",
            f"  * '· Key point' → '· Point clé' (translate text, keep bullet)",
            f"  * '- Important note' → '- Note importante' (translate text, keep bullet)",
            "- DO NOT return the source text unchanged - always provide a translation.",
        ])
    
    lines.extend([
        "10. For short text blocks (headers, bullets, titles):",
        "    - Translate EVERY word - do not skip or omit anything",
        "    - Even single words like 'Conclusion' or 'Section 4' must be translated",
        "    - Short phrases like '· Key point' must be fully translated",
        "",
        "FORBIDDEN: Do NOT return responses like:",
        "- 'Je suis ravi de vous aider' (I'm happy to help)",
        "- 'Pouvez-vous...' (Can you...)",
        "- 'Comment puis-je...' (How can I...)",
        "- Any greeting or explanation text",
        "",
        "IMPORTANT: If the text appears to already be in the target language, translate it anyway to ensure accuracy.",
    ])
    if glossary:
        lines += ["", "GLOSSARY (must follow exactly):"]
        for k, v in glossary.items():
            lines.append(f"- {k} -> {v}")
    return "\n".join(lines)
