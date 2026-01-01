"""
Export translated documents to LaTeX format.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def export_to_latex(
    translations: dict[str, str],
    source_pdf: str,
    output_path: str,
    source_lang: str = "en",
    target_lang: str = "fr",
) -> bool:
    """
    Export translations to LaTeX document.

    Args:
        translations: Dict mapping block_id to translated text
        source_pdf: Path to source PDF
        output_path: Path for output LaTeX file
        source_lang: Source language code
        target_lang: Target language code

    Returns:
        True if successful, False otherwise
    """
    try:
        latex_content = f"""\\documentclass[11pt]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{babel}}
\\usepackage{{geometry}}
\\geometry{{a4paper, margin=2.5cm}}

\\title{{Translation: {source_lang} → {target_lang}}}
\\author{{SciTrans}}
\\date{{\\today}}

\\begin{{document}}

\\maketitle

\\section*{{Metadata}}
\\begin{{itemize}}
    \\item Source: {Path(source_pdf).name}
    \\item Total blocks: {len(translations)}
\\end{{itemize}}

\\newpage

\\section{{Translations}}

"""

        # Add translations
        for block_id, translated_text in translations.items():
            # Escape LaTeX special characters
            escaped_text = (
                translated_text.replace("\\", "\\textbackslash{}")
                .replace("{", "\\{")
                .replace("}", "\\}")
                .replace("$", "\\$")
                .replace("&", "\\&")
                .replace("%", "\\%")
                .replace("#", "\\#")
                .replace("^", "\\textasciicircum{}")
                .replace("_", "\\_")
                .replace("~", "\\textasciitilde{}")
            )

            latex_content += f"\\subsection*{{Block: {block_id}}}\n"
            latex_content += f"{escaped_text}\n\n"

        latex_content += "\\end{document}\n"

        # Save
        Path(output_path).write_text(latex_content, encoding="utf-8")
        logger.info(f"Exported to LaTeX: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export to LaTeX: {e}")
        return False
