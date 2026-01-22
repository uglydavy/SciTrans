"""Parallel translation executor for multiple blocks.

This module provides threading support for translating multiple blocks concurrently,
significantly speeding up translation for large documents.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable, Optional

from rich.console import Console

from scitrans.core.models import MaskedBlock
from scitrans.translation.backends.base import TranslationBackend, TranslateRequest

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class TranslationTask:
    """A single translation task."""
    block_id: str
    masked_block: MaskedBlock
    request: TranslateRequest
    backend: TranslationBackend


@dataclass
class TranslationResult:
    """Result of a translation task."""
    block_id: str
    candidates: list[str]
    meta: dict[str, Any]
    error: Optional[str] = None


def translate_block_worker(task: TranslationTask) -> TranslationResult:
    """Worker function to translate a single block.
    
    This runs in a separate thread and handles one block translation.
    """
    try:
        res = task.backend.translate(task.request)
        candidates = res.candidates if res.candidates else [""]
        meta = {
            "backend": task.backend.name,
            "model": getattr(task.backend, "model", "unknown"),
            "cached": False,
            **res.meta,
        }
        return TranslationResult(
            block_id=task.block_id,
            candidates=candidates,
            meta=meta,
        )
    except Exception as e:
        logger.error(f"Block {task.block_id}: Translation failed in worker: {e}", exc_info=True)
        return TranslationResult(
            block_id=task.block_id,
            candidates=[""],
            meta={
                "backend": task.backend.name,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            error=str(e),
        )


def translate_blocks_parallel(
    masked_blocks: list[MaskedBlock],
    backend: TranslationBackend,
    build_request_fn: Callable[[MaskedBlock], TranslateRequest],
    max_workers: int = 4,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> dict[str, TranslationResult]:
    """Translate multiple blocks in parallel using threading.
    
    Args:
        masked_blocks: List of masked blocks to translate
        backend: Translation backend to use
        build_request_fn: Function that takes a MaskedBlock and returns TranslateRequest
        max_workers: Maximum number of parallel workers
        progress_callback: Optional callback(progress: float, desc: str) for progress updates
    
    Returns:
        Dict mapping block_id to TranslationResult
    """
    if not masked_blocks:
        return {}
    
    logger.info(f"Starting parallel translation of {len(masked_blocks)} blocks with {max_workers} workers")
    console.print(f"[cyan]🔄 Translating {len(masked_blocks)} blocks in parallel ({max_workers} workers)...[/cyan]")
    
    # Build tasks
    tasks = []
    for mb in masked_blocks:
        req = build_request_fn(mb)
        task = TranslationTask(
            block_id=mb.block_id,
            masked_block=mb,
            request=req,
            backend=backend,
        )
        tasks.append(task)
    
    # Execute in parallel
    results: dict[str, TranslationResult] = {}
    completed = 0
    total = len(tasks)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {executor.submit(translate_block_worker, task): task for task in tasks}
        
        # Collect results as they complete
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
                results[result.block_id] = result
                completed += 1
                
                # Update progress
                if progress_callback:
                    progress = 0.3 + (completed / total) * 0.5  # 30% to 80% of total
                    progress_callback(progress, f"Translated {completed}/{total} blocks...")
                
                # Log result
                if result.candidates and result.candidates[0]:
                    logger.info(f"Block {result.block_id}: Parallel translation completed ({len(result.candidates[0])} chars)")
                else:
                    logger.warning(f"Block {result.block_id}: Parallel translation returned empty")
                    
            except Exception as e:
                logger.error(f"Block {task.block_id}: Future exception: {e}", exc_info=True)
                results[task.block_id] = TranslationResult(
                    block_id=task.block_id,
                    candidates=[""],
                    meta={"error": str(e)},
                    error=str(e),
                )
                completed += 1
    
    logger.info(f"Parallel translation complete: {len(results)}/{total} blocks translated")
    return results

