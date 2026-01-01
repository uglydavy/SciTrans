"""
Parallel translation helper functions for pipeline.

This module provides parallel translation capabilities while respecting
context window dependencies.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from scitrans.core.models import MaskedBlock
from scitrans.translation.backends.base import TranslateRequest, TranslationBackend

logger = logging.getLogger(__name__)


def translate_block_parallel(
    mb: MaskedBlock,
    backend: TranslationBackend,
    req_factory: Callable[[MaskedBlock, str], TranslateRequest],
    context_text: str = "",
) -> tuple[str, dict]:
    """
    Translate a single block (for parallel execution).

    Returns:
        Tuple of (translated_text, metadata)
    """
    try:
        req = req_factory(mb, context_text)
        res = backend.translate(req)
        candidates = res.candidates if res.candidates else [""]
        meta = {
            "backend": backend.name,
            "model": getattr(backend, "model", "unknown"),
            "cached": False,
            **res.meta,
        }
        return candidates[0] if candidates else "", meta
    except Exception as e:
        logger.warning(f"Translation failed for block {mb.block_id}: {e}")
        return "", {
            "backend": backend.name,
            "model": getattr(backend, "model", "unknown"),
            "cached": False,
            "error": str(e),
        }


def translate_blocks_parallel(
    masked_blocks: list[MaskedBlock],
    backend: TranslationBackend,
    req_factory: Callable[[MaskedBlock, str], TranslateRequest],
    max_workers: int = 4,
    context_window: int = 0,
) -> list[tuple[MaskedBlock, str, dict]]:
    """
    Translate blocks in parallel while respecting context window.

    Strategy:
    - If context_window == 0: Translate all blocks in parallel
    - If context_window > 0: Use sliding window approach
      - Process blocks in batches
      - Each batch can be parallelized
      - Next batch depends on previous batch

    Returns:
        List of (MaskedBlock, translated_text, metadata) tuples in original order
    """
    if context_window == 0:
        # No context dependencies - full parallelization
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(translate_block_parallel, mb, backend, req_factory, ""): mb
                for mb in masked_blocks
            }

            for future in as_completed(futures):
                mb = futures[future]
                try:
                    translated, meta = future.result()
                    results[mb.block_id] = (mb, translated, meta)
                except Exception as e:
                    logger.error(f"Error translating block {mb.block_id}: {e}")
                    results[mb.block_id] = (mb, "", {"error": str(e)})

        # Return in original order
        return [results[mb.block_id] for mb in masked_blocks]

    else:
        # Context window creates dependencies - use sliding window
        results = {}
        context_buffer: list[str] = []

        # Process in batches
        batch_size = max(1, max_workers)

        for i in range(0, len(masked_blocks), batch_size):
            batch = masked_blocks[i : i + batch_size]

            # Build context for this batch
            context_text = ""
            if context_buffer:
                context_parts = context_buffer[-context_window:]
                context_text = "\n\n".join(context_parts)

            # Translate batch in parallel
            batch_results = {}
            with ThreadPoolExecutor(max_workers=min(len(batch), max_workers)) as executor:
                futures = {
                    executor.submit(
                        translate_block_parallel, mb, backend, req_factory, context_text
                    ): mb
                    for mb in batch
                }

                for future in as_completed(futures):
                    mb = futures[future]
                    try:
                        translated, meta = future.result()
                        batch_results[mb.block_id] = (mb, translated, meta)
                    except Exception as e:
                        logger.error(f"Error translating block {mb.block_id}: {e}")
                        batch_results[mb.block_id] = (mb, "", {"error": str(e)})

            # Update results and context buffer
            for mb in batch:
                mb_result, translated, meta = batch_results[mb.block_id]
                results[mb.block_id] = (mb_result, translated, meta)
                if translated.strip():
                    context_buffer.append(translated)
                    if len(context_buffer) > context_window * 2:
                        context_buffer = context_buffer[-context_window:]

        # Return in original order
        return [results[mb.block_id] for mb in masked_blocks]
