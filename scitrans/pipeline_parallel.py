"""
Parallel Translation Pipeline

Provides parallel block translation for improved performance on large documents.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional

from scitrans.core.models import MaskedBlock
from scitrans.translation.backends.base import TranslationBackend, TranslateRequest

logger = logging.getLogger(__name__)


def translate_block_parallel(
    mb: MaskedBlock,
    backend: TranslationBackend,
    translate_func: Callable[[MaskedBlock], tuple[list[str], dict]],
    block_index: int,
    total_blocks: int,
) -> tuple[MaskedBlock, list[str], dict, Optional[Exception]]:
    """
    Translate a single block (for use in parallel execution).

    Args:
        mb: Masked block to translate
        backend: Translation backend
        translate_func: Function that performs the actual translation
        block_index: Index of this block (for logging)
        total_blocks: Total number of blocks (for logging)

    Returns:
        Tuple of (masked_block, candidates, metadata, error)
    """
    try:
        logger.debug(f"Parallel: Translating block {mb.block_id} ({block_index+1}/{total_blocks})")
        candidates, metadata = translate_func(mb)
        return mb, candidates, metadata, None
    except Exception as e:
        logger.error(f"Parallel: Error translating block {mb.block_id}: {e}", exc_info=True)
        return mb, [], {"error": str(e), "error_type": type(e).__name__}, e


def run_parallel_translation(
    masked_blocks: list[MaskedBlock],
    translate_func: Callable[[MaskedBlock], tuple[list[str], dict]],
    backend: TranslationBackend,
    max_workers: int = 4,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict[str, tuple[list[str], dict]]:
    """
    Translate blocks in parallel using ThreadPoolExecutor.

    Args:
        masked_blocks: List of masked blocks to translate
        translate_func: Function that translates a single block
        backend: Translation backend (for logging)
        max_workers: Maximum number of parallel workers
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        Dictionary mapping block_id -> (candidates, metadata)
    """
    if not masked_blocks:
        return {}

    logger.info(f"Starting parallel translation of {len(masked_blocks)} blocks with {max_workers} workers")

    results: dict[str, tuple[list[str], dict]] = {}
    completed = 0
    errors = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_block = {
            executor.submit(
                translate_block_parallel,
                mb,
                backend,
                translate_func,
                idx,
                len(masked_blocks),
            ): mb
            for idx, mb in enumerate(masked_blocks)
        }

        # Process completed tasks as they finish
        for future in as_completed(future_to_block):
            mb = future_to_block[future]
            try:
                _, candidates, metadata, error = future.result()

                if error:
                    errors += 1
                    logger.warning(f"Block {mb.block_id} failed: {error}")
                    results[mb.block_id] = ([], metadata)
                else:
                    results[mb.block_id] = (candidates, metadata)
                    logger.debug(f"Block {mb.block_id} completed: {len(candidates)} candidates")

                completed += 1
                if progress_callback:
                    progress_callback(completed, len(masked_blocks))

            except Exception as e:
                errors += 1
                logger.error(f"Unexpected error processing block {mb.block_id}: {e}", exc_info=True)
                results[mb.block_id] = ([], {"error": str(e), "error_type": type(e).__name__})

    logger.info(
        f"Parallel translation complete: {completed}/{len(masked_blocks)} blocks, "
        f"{errors} errors, {len(masked_blocks) - completed} remaining"
    )

    return results

