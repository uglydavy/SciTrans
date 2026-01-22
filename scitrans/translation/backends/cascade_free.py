from __future__ import annotations

import re
import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


class CascadeFreeBackend:
    """Cascade free backend combining multiple strong free models.

    Strategy:
    1. Generate translations from multiple free backends:
       - Ollama (if available locally)
       - Google Translate (free)
    2. Uses BOTH ollama & google together (not fallback - both run in parallel)
    3. Use reranking to select best translation
    4. Apply glossary enforcement
    5. Use caching for efficiency

    This provides production-quality results at zero API cost.
    
    NOTE: cascade_free uses ollama & google TOGETHER (parallel execution).
    Other backends (openai, deepseek, etc.) only fallback to ollama/google
    if the primary backend fails or is unavailable.
    """

    name = "cascade_free"

    def __init__(self, model: str = "cascade_free"):
        self.model = model

        # Initialize available backends (prioritize working free backends)
        self._backends: list[tuple[str, object]] = []

        # Try Google Translate (free, no key required)
        try:
            from scitrans.translation.backends.google_backend import GoogleTranslateBackend

            self._backends.append(("google", GoogleTranslateBackend()))
            import logging
            logging.getLogger(__name__).info("cascade_free: Google Translate backend initialized")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"cascade_free: Failed to initialize Google Translate: {e}")

        # Try Ollama (local, if running)
        try:
            import requests

            from scitrans.translation.backends.ollama_backend import OllamaBackend

            # Check if Ollama is actually running before adding
            try:
                requests.get("http://localhost:11434/api/tags", timeout=2)
                self._backends.append(("ollama", OllamaBackend(model="llama3.2")))
                import logging
                logging.getLogger(__name__).info("cascade_free: Ollama backend initialized")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"cascade_free: Ollama not available: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"cascade_free: Failed to check Ollama: {e}")

        # Log which backends were initialized
        import logging
        logger = logging.getLogger(__name__)
        backend_names = [name for name, _ in self._backends]
        logger.info(f"cascade_free initialized with {len(self._backends)} backends: {backend_names}")
        
        if not self._backends:
            raise RuntimeError(
                "No free backends available. Please set up at least one:\n\n"
                "Option 1: Google Translate (free, basic quality)\n"
                "  pip install googletrans==4.0.0rc1\n\n"
                "Option 2: Ollama (local, offline)\n"
                "  Install from https://ollama.ai/ and run 'ollama serve'\n\n"
                f"Currently initialized backends: {len(self._backends)}"
            )
        
        # Ensure we have at least Google (should always be available)
        has_google = any(name == "google" for name, _ in self._backends)
        has_ollama = any(name == "ollama" for name, _ in self._backends)
        
        if not has_google:
            logger.warning("cascade_free: Google Translate not available - this is unusual")
        if not has_ollama:
            logger.warning("cascade_free: Ollama not available - make sure 'ollama serve' is running")
        
        if has_google and has_ollama:
            logger.info("cascade_free: Using both Google Translate and Ollama together (parallel execution)")
        elif has_google:
            logger.warning("cascade_free: Only Google Translate available - quality may be lower")
        elif has_ollama:
            logger.warning("cascade_free: Only Ollama available - consider adding Google Translate for better coverage")

    def _is_identity_translation(self, source: str, translation: str, threshold: float = 0.90, is_header: bool = False) -> bool:
        """Check if translation is identical or too similar to source (identity translation).
        
        For headers with section numbers, compares only the content AFTER the prefix
        to allow proper preservation of section numbering.
        
        Args:
            source: Source text
            translation: Translated text
            threshold: Similarity threshold (0-1). Higher = stricter (less permissive)
                      Default 0.90, academic content uses 0.95, headers use 0.98
            is_header: Whether this is a header/title block
            
        Returns True if the translation is essentially unchanged from source.
        """
        if not source or not translation:
            return False
        
        # WHITELIST CHECK: If text contains technical terms, allow identity
        # Technical terms like "GPT-3", "DALL-E", "RLHF" are valid when identical
        from scitrans.utils.content_detector import contains_whitelisted_terms
        if contains_whitelisted_terms(source) or contains_whitelisted_terms(translation):
            # Contains technical terms - very permissive (99% threshold)
            threshold = 0.99
        
        # Normalize whitespace and case for comparison
        source_norm = " ".join(source.lower().split())
        trans_norm = " ".join(translation.lower().split())
        
        # For headers with section numbers, compare only the content after the prefix
        if is_header:
            section_pattern = r'^(section|chapter|part|chapitre|partie)\s+\d+\s*:?\s*'
            source_content = re.sub(section_pattern, '', source_norm, flags=re.IGNORECASE)
            trans_content = re.sub(section_pattern, '', trans_norm, flags=re.IGNORECASE)
            
            # If both have section prefixes, compare only content
            if source_content != source_norm or trans_content != trans_norm:
                # At least one has a section prefix - compare content only
                try:
                    from difflib import SequenceMatcher
                    similarity = SequenceMatcher(None, source_content, trans_content).ratio()
                    # Use configurable threshold (default 0.95 for headers, can be 0.98 for academic)
                    header_threshold = max(threshold, 0.95) if threshold < 0.95 else threshold
                    if similarity > header_threshold:
                        return True
                    return False
                except Exception:
                    # If comparison fails, fall through to standard check
                    pass
        
        # Standard comparison for non-headers or headers without section numbers
        # If exactly the same (case-insensitive), it's identity
        if source_norm == trans_norm:
            return True
        
        # Use configurable threshold (passed from request)
        try:
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, source_norm, trans_norm).ratio()
            if similarity > threshold:
                return True
        except Exception:
            pass
        
        return False
    
    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()
        candidates: list[str] = []
        backend_info: list[dict] = []
        
        import logging
        logger = logging.getLogger(__name__)

        # Quality priority: Ollama > Google
        # Sort backends by quality priority (Ollama first, Google last)
        backend_priority = {"ollama": 0, "google": 1}
        sorted_backends = sorted(self._backends, key=lambda x: backend_priority.get(x[0], 99))
        logger.info(f"cascade_free: Using {len(sorted_backends)} backends: {[name for name, _ in sorted_backends]}")

        # Collect translations from all available backends (prioritize quality)
        # Use threading.Thread instead of ThreadPoolExecutor to avoid nested executor issues
        # when called from parallel translation pipeline
        import threading
        from queue import Queue
        
        candidates_with_source = []  # Store (candidate, backend_name, priority)
        result_queue = Queue()
        
        def translate_with_backend(backend_name, backend, priority):
            """Translate using a specific backend and return result with metadata."""
            backend_start = time.time()
            # PHASE 3.2: Keep 3 retries for quality (reducing to 1 caused too many failures)
            # Speed comes from increased threshold (90/95%), not from skipping retries
            max_retries = 3
            retry_count = 0
            
            try:
                # Detect if this is a header block (requires stricter validation)
                # Handle context as dict (new) or legacy string (backward compatibility)
                if isinstance(req.context, dict):
                    is_header = req.context.get("is_header", False)
                else:
                    # Legacy string context or empty - can't determine header status
                    is_header = False
                
                while retry_count < max_retries:
                    # Build retry-specific prompt
                    current_prompt = req.system_prompt
                    if retry_count > 0:
                        # Escalating prompts for retries
                        if retry_count == 1:
                            current_prompt += f"\n\n🚨 CRITICAL RETRY #{retry_count}: You MUST translate from {req.source_lang} to {req.target_lang}. DO NOT return text unchanged! Output MUST be in {req.target_lang}."
                        elif retry_count == 2:
                            current_prompt += f"\n\n⚠️ FINAL RETRY #{retry_count}: This is your LAST CHANCE. You MUST translate the text to {req.target_lang}. Returning source text is FORBIDDEN."
                    
                    # For headers, add extra emphasis even on first try
                    if is_header and retry_count == 0:
                        current_prompt += f"\n\n🎯 HEADER TRANSLATION REQUIRED: This is a document header/title in {req.source_lang}. You MUST translate it to {req.target_lang}. REQUIRED."
                    
                    # Create request with current prompt
                    current_req = TranslateRequest(
                        text=req.text,
                        source_lang=req.source_lang,
                        target_lang=req.target_lang,
                        system_prompt=current_prompt,
                        temperature=min(req.temperature + (0.2 * retry_count), 0.95),  # Increase temperature per retry
                        n_candidates=req.n_candidates,
                        context=req.context,
                    )
                    
                    # Call backend
                    result = backend.translate(current_req)
                    
                    if result and result.candidates and result.candidates[0]:
                        candidate = result.candidates[0]
                        
                        # Filter empty/None candidates
                        if not candidate or not candidate.strip():
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.warning(
                                    f"cascade_free: {backend_name} returned empty candidate "
                                    f"(attempt {retry_count}/{max_retries})\n"
                                    f"  Request text length: {len(req.text)} chars\n"
                                    f"  Request timeout: {req.timeout}s\n"
                                    f"  Action: Retrying with higher temperature..."
                                )
                                time.sleep(0.1)
                                continue
                            else:
                                logger.error(
                                    f"cascade_free: {backend_name} still returning empty after {max_retries} retries\n"
                                    f"  Request text: '{req.text[:100]}...'\n"
                                    f"  Total attempts: {max_retries}\n"
                                    f"  Error: Empty translation returned"
                                )
                                result_queue.put((None, backend_name, priority, False, "Empty translation"))
                                return
                        
                        # Check for identity translation (context-aware for headers)
                        # Use threshold from request (default 0.90, academic 0.95, header 0.98)
                        threshold = req.identity_threshold if hasattr(req, 'identity_threshold') else 0.90
                        if self._is_identity_translation(req.text, candidate, threshold=threshold, is_header=is_header):
                            retry_count += 1
                            if retry_count < max_retries:
                                logger.warning(f"cascade_free: {backend_name} returned identity translation (attempt {retry_count}/{max_retries}), retrying...")
                                time.sleep(0.1)  # Brief pause before retry
                                continue
                            else:
                                logger.error(f"cascade_free: {backend_name} still returning identity translation after {max_retries} retries - MARKING AS FAILED")
                                # For headers, this is a hard failure - don't accept identity
                                if is_header:
                                    result_queue.put((None, backend_name, priority, False, "Identity translation (header)"))
                                    return
                                # For non-headers, we'll still mark as failed but return the candidate for potential fallback
                                result_queue.put((candidate, backend_name, priority, False, f"Identity translation after {max_retries} retries"))
                                return
                        
                        # Valid translation found
                        if retry_count > 0:
                            logger.info(f"cascade_free: {backend_name} retry #{retry_count} successful - got valid translation")
                        logger.info(f"cascade_free: {backend_name} returned {len(candidate)} chars in {time.time() - backend_start:.2f}s")
                        result_queue.put((candidate, backend_name, priority, True, None))
                        return
                    
                    # No candidates - retry
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"cascade_free: {backend_name} returned no candidates (attempt {retry_count}/{max_retries}), retrying...")
                        time.sleep(0.1)
                        continue
                    
                logger.warning(f"cascade_free: {backend_name} returned no candidates after {max_retries} attempts")
                result_queue.put((None, backend_name, priority, False, "No candidates"))
            except Exception as e:
                backend_latency = time.time() - backend_start
                error_type = type(e).__name__
                logger.error(
                    f"cascade_free: {backend_name} failed after {backend_latency:.2f}s\n"
                    f"  Error type: {error_type}\n"
                    f"  Error message: {str(e)}\n"
                    f"  Request text length: {len(req.text)} chars\n"
                    f"  Request timeout: {req.timeout}s\n"
                    f"  Attempts made: {retry_count + 1}/{max_retries}",
                    exc_info=True
                )
                result_queue.put((None, backend_name, priority, False, f"{error_type}: {str(e)}"))

        # Execute all backends concurrently using threading.Thread (avoids nested executor issues)
        threads = []
        for name, be in sorted_backends:
            thread = threading.Thread(
                target=translate_with_backend,
                args=(name, be, backend_priority.get(name, 99)),
                daemon=True
            )
            thread.start()
            threads.append((thread, name))
        
        # PHASE 2: Use timeout from request (calculated per-request in pipeline)
        # If request has timeout field, use it; otherwise calculate adaptively
        # Ensure timeout is at least 60s to match backend minimums (Google: 30s, Ollama: 60s)
        if hasattr(req, 'timeout') and req.timeout:
            max_wait_time = max(60.0, req.timeout)  # Ensure minimum 60s
            logger.info(f"cascade_free: Using request timeout = {max_wait_time:.1f}s")
        else:
            # Fallback: Adaptive timeout based on text length
            text_length = len(req.text)
            estimated_ollama_time = max(10.0, (text_length / 100) * 10)  # 10s per 100 chars
            max_wait_time = max(60.0, estimated_ollama_time * 1.5)
            logger.info(f"cascade_free: Calculated timeout = {max_wait_time:.1f}s for {text_length} chars")
        
        # Wait for all threads with adaptive timeout
        overall_start = time.time()
        completed_backends = set()
        
        while len(completed_backends) < len(sorted_backends) and (time.time() - overall_start) < max_wait_time:
            try:
                # Wait for result with timeout (check every 2 seconds)
                remaining_time = max_wait_time - (time.time() - overall_start)
                if remaining_time <= 0:
                    break
                timeout = min(2.0, remaining_time)  # Check every 2s or remaining time
                candidate, backend_name, priority, success, error = result_queue.get(timeout=timeout)
                completed_backends.add(backend_name)
                
                if success and candidate:
                    candidates_with_source.append((candidate, backend_name, priority))
                    backend_info.append({
                        "backend": backend_name,
                        "success": True,
                        "quality_priority": priority,
                    })
                else:
                    backend_info.append({
                        "backend": backend_name,
                        "success": False,
                        "error": error or "No candidates",
                    })
            except Exception:
                # Queue timeout - check if threads are still alive
                elapsed = time.time() - overall_start
                if elapsed >= max_wait_time:
                    break
                # Check for completed threads that didn't put results
                for thread, name in threads:
                    if not thread.is_alive() and name not in completed_backends:
                        # Thread finished but didn't put result - mark as failed
                        completed_backends.add(name)
                        backend_info.append({
                            "backend": name,
                            "success": False,
                            "error": "Thread completed without result",
                        })
        
        # Mark any remaining threads as timed out
        for thread, name in threads:
            if name not in completed_backends:
                if thread.is_alive():
                    elapsed = time.time() - overall_start
                    logger.warning(
                        f"cascade_free: {name} still running after timeout - marking as failed\n"
                        f"  Timeout limit: {max_wait_time:.1f}s\n"
                        f"  Elapsed time: {elapsed:.1f}s\n"
                        f"  Request text length: {len(req.text)} chars\n"
                        f"  Action: Marking as failed, will try other backends"
                    )
                    backend_info.append({
                        "backend": name,
                        "success": False,
                        "error": f"Timeout ({max_wait_time:.1f}s overall, {elapsed:.1f}s elapsed)",
                    })
                else:
                    backend_info.append({
                        "backend": name,
                        "success": False,
                        "error": "Thread completed without result",
                    })

        # Sort candidates by quality priority (lower number = higher quality)
        candidates_with_source.sort(key=lambda x: x[2])
        candidates = [c[0] for c in candidates_with_source]
        if not candidates:
            # All backends failed - log this with detailed information
            failed_backends = [b for b in backend_info if not b.get("success")]
            error_summary = "\n".join(
                f"  - {b['backend']}: {b.get('error', 'Unknown error')}"
                for b in failed_backends
            )
            logger.error(
                f"cascade_free: ALL backends failed!\n"
                f"  Request text: '{req.text[:100]}...'\n"
                f"  Request length: {len(req.text)} chars\n"
                f"  Backends attempted: {len(backend_info)}\n"
                f"  Failed backends:\n{error_summary}\n"
                f"  Action: Returning empty result (will trigger emergency retry)"
            )
            # Fallback: return empty
            candidates = [""]

        latency = time.time() - start

        # Log warning if only Google Translate is available (low quality)
        successful_backends = [b["backend"] for b in backend_info if b.get("success")]
        if successful_backends == ["google"]:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                "⚠️ Only Google Translate available. Quality may be poor for scientific content. "
                "Consider setting up Ollama (local) for better quality: https://ollama.ai/"
            )

        return TranslateResult(
            candidates=candidates,  # Reranking happens at pipeline level
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "backends_used": backend_info,
                "num_candidates": len(candidates),
                "note": "Free cascade backend - multiple models combined",
                "warning": "Low quality expected" if successful_backends == ["google"] else None,
            },
        )
    
    def _calculate_batch_timeout(self, num_requests: int, avg_text_length: int) -> float:
        """Calculate adaptive timeout based on batch size and text complexity.
        
        Formula: base_time + (requests * per_request_time * parallel_factor)
        - base_time: 30s (overhead for batch setup)
        - per_request_time: 10s per 100 chars
        - parallel_factor: 0.3 (accounts for 32 workers running in parallel)
        
        Examples:
        - 32 requests, 100 chars: 30 + (32 * 1.0 * 0.3) = 40s
        - 64 requests, 200 chars: 30 + (64 * 2.0 * 0.3) = 68s  
        - 96 requests, 150 chars: 30 + (96 * 1.5 * 0.3) = 73s
        - 854 requests, 200 chars: 30 + (854 * 2.0 * 0.3) = 543s (~9 min)
        
        Args:
            num_requests: Number of requests in batch
            avg_text_length: Average text length across requests
            
        Returns:
            Timeout in seconds (minimum 60s)
        """
        base_time = 30.0
        per_request = (avg_text_length / 100.0) * 10.0
        parallel_factor = 0.3  # We run up to 32 workers in parallel
        
        timeout = base_time + (num_requests * per_request * parallel_factor)
        return max(60.0, timeout)  # Minimum 60s
    
    def translate_batch(self, requests: list[TranslateRequest]) -> list[TranslateResult]:
        """Translate multiple requests in parallel across backends.
        
        This significantly improves performance for documents with many blocks.
        
        Strategy:
        1. Group requests into batches
        2. Process each batch with all backends in parallel
        3. Collect results as they complete
        4. Return results in original order
        
        Args:
            requests: List of translation requests
            
        Returns:
            List of translation results in same order as input requests
        """
        if not requests:
            return []
        
        import logging
        
        logger = logging.getLogger(__name__)
        logger.info(f"cascade_free: Batch translating {len(requests)} requests")
        
        # Calculate adaptive timeout based on batch size
        avg_text_length = sum(len(req.text) for req in requests) / len(requests)
        batch_timeout = self._calculate_batch_timeout(len(requests), int(avg_text_length))
        logger.info(f"cascade_free: Batch timeout set to {batch_timeout:.0f}s (avg text: {avg_text_length:.0f} chars)")
        
        # Use ThreadPoolExecutor for parallel processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # Process all requests in parallel (each calls translate() which handles backend parallelism)
        results = [None] * len(requests)  # Preserve order
        
        # PHASE 6.1 & 6.2: Increase parallelism for better speed
        # Use more workers: up to 32 parallel requests, or 4x CPU count
        import os
        max_workers = min(32, len(requests), os.cpu_count() * 4 if os.cpu_count() else 8)
        
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all requests
            future_to_index = {
                executor.submit(self.translate, req): idx
                for idx, req in enumerate(requests)
            }
            
            # Collect results as they complete
            completed = 0
            for future in as_completed(future_to_index):
                idx = future_to_index[future]
                try:
                    # Use adaptive timeout (was fixed 60s)
                    result = future.result(timeout=batch_timeout)
                    results[idx] = result
                    completed += 1
                    if completed % 5 == 0:  # Log progress every 5 requests
                        logger.info(f"cascade_free: Batch progress: {completed}/{len(requests)} completed")
                except Exception as e:
                    logger.error(f"cascade_free: Request {idx} failed: {e}", exc_info=True)
                    # Return empty result for failed request
                    results[idx] = TranslateResult(
                        candidates=[""],
                        model=self.model,
                        backend=self.name,
                        meta={"error": str(e), "batch_failure": True},
                    )
        
        batch_time = time.time() - start_time
        logger.info(f"cascade_free: Batch translation completed: {len(requests)} requests in {batch_time:.2f}s ({batch_time/len(requests):.2f}s avg)")
        
        return results
