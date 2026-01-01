"""
Export translated documents to JSON format.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def export_to_json(
    translations: dict[str, str],
    source_pdf: str,
    output_path: str,
    source_lang: str = "en",
    target_lang: str = "fr",
    metadata: dict[str, Any] | None = None,
) -> bool:
    """
    Export translations to JSON format.

    Args:
        translations: Dict mapping block_id to translated text
        source_pdf: Path to source PDF
        output_path: Path for output JSON file
        source_lang: Source language code
        target_lang: Target language code
        metadata: Additional metadata to include

    Returns:
        True if successful, False otherwise
    """
    try:
        export_data = {
            "metadata": {
                "source_pdf": str(Path(source_pdf).name),
                "source_lang": source_lang,
                "target_lang": target_lang,
                "total_blocks": len(translations),
                **(metadata or {}),
            },
            "translations": [
                {
                    "block_id": block_id,
                    "translated_text": translated_text,
                }
                for block_id, translated_text in translations.items()
            ],
        }

        # Save
        Path(output_path).write_text(
            json.dumps(export_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Exported to JSON: {output_path}")
        return True

    except Exception as e:
        logger.error(f"Failed to export to JSON: {e}")
        return False
