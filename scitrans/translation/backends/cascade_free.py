from __future__ import annotations

import os
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
        
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:89","message":"Cascade free backends initialized","data":{"num_backends":len(sorted_backends),"backends":[name for name, _ in sorted_backends],"text_preview":req.text[:50]}})+'\n')
        # #endregion
        
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
            try:
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:142","message":"Calling backend","data":{"backend_name":backend_name,"text_preview":req.text[:50]}})+'\n')
                # #endregion
                
                # Call backend directly (this function is already running in a thread)
                result = backend.translate(req)
                
                if result and result.candidates and result.candidates[0]:
                    candidate_preview = result.candidates[0][:100]
                    backend_latency = time.time() - backend_start
                    # #region agent log
                    with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                        import json
                        f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:185","message":"Backend succeeded","data":{"backend_name":backend_name,"candidate_len":len(result.candidates[0]),"candidate_preview":candidate_preview,"latency_s":backend_latency}})+'\n')
                    # #endregion
                    logger.info(f"cascade_free: {backend_name} returned {len(result.candidates[0])} chars in {backend_latency:.2f}s")
                    result_queue.put((result.candidates[0], backend_name, priority, True, None))
                    return
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:191","message":"Backend returned no candidates","data":{"backend_name":backend_name,"num_candidates":len(result.candidates) if result and result.candidates else 0}})+'\n')
                # #endregion
                logger.warning(f"cascade_free: {backend_name} returned no candidates")
                result_queue.put((None, backend_name, priority, False, "No candidates"))
            except Exception as e:
                backend_latency = time.time() - backend_start
                # #region agent log
                with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
                    import json
                    f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:197","message":"Backend failed","data":{"backend_name":backend_name,"error":str(e),"error_type":type(e).__name__,"latency_s":backend_latency}})+'\n')
                # #endregion
                logger.error(f"cascade_free: {backend_name} failed after {backend_latency:.2f}s: {e}", exc_info=True)
                result_queue.put((None, backend_name, priority, False, str(e)))

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
        
        # Wait for all threads with timeout (30s per backend, 45s overall to prevent hanging)
        overall_start = time.time()
        completed_backends = set()
        max_wait_time = 45.0  # Overall timeout reduced to 45s (Google is too slow)
        
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
                    logger.warning(f"cascade_free: {name} still running after timeout - marking as failed")
                    backend_info.append({
                        "backend": name,
                        "success": False,
                        "error": f"Timeout ({max_wait_time}s overall)",
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
        
        # #region agent log
        with open('/Users/kv.kn/Desktop/Research/SciTrans_fixed/.cursor/debug.log', 'a') as f:
            import json
            f.write(json.dumps({"sessionId":"debug-session","runId":"pre-fix","hypothesisId":"C","location":"cascade_free.py:138","message":"Cascade free results","data":{"num_candidates":len(candidates),"successful_backends":[b["backend"] for b in backend_info if b.get("success")],"failed_backends":[b["backend"] for b in backend_info if not b.get("success")],"backend_errors":{b["backend"]:b.get("error") for b in backend_info if not b.get("success")}}})+'\n')
        # #endregion

        if not candidates:
            # All backends failed - log this
            logger.error(f"cascade_free: ALL backends failed! Errors: {[b.get('error') for b in backend_info]}")
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
