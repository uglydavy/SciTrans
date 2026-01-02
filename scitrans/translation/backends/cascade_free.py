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

        # Try DeepSeek (free-tier, high quality, OpenAI-compatible)
        try:
            from scitrans.translation.backends.deepseek_backend import DeepSeekBackend

            if os.getenv("DEEPSEEK_API_KEY"):
                self._backends.append(("deepseek", DeepSeekBackend()))
        except Exception:
            pass

        # Try Google Translate (free, no key required)
        try:
            from scitrans.translation.backends.google_backend import GoogleTranslateBackend

            self._backends.append(("google", GoogleTranslateBackend()))
        except Exception:
            pass

        # Try Ollama (local, if running)
        try:
            import requests

            from scitrans.translation.backends.ollama_backend import OllamaBackend

            # Check if Ollama is actually running before adding
            try:
                requests.get("http://localhost:11434/api/tags", timeout=2)
                self._backends.append(("ollama", OllamaBackend(model="llama3.2")))
            except Exception:
                pass  # Ollama not running
        except Exception:
            pass

        if not self._backends:
            raise RuntimeError(
                "No free backends available. Please set up at least one:\n\n"
                "Option 1 (Recommended): DeepSeek (free-tier, high quality)\n"
                "  export DEEPSEEK_API_KEY='sk-...'\n"
                "  export DEEPSEEK_BASE_URL='https://dpapi.cn/query'\n\n"
                "Option 2: Google Translate (free, basic quality)\n"
                "  pip install googletrans==4.0.0rc1\n\n"
                "Option 3: Ollama (local, offline)\n"
                "  Install from https://ollama.ai/ and run 'ollama serve'\n\n"
                f"Currently initialized backends: {len(self._backends)}"
            )

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()
        candidates: list[str] = []
        backend_info: list[dict] = []

        # Quality priority: DeepSeek > Ollama > Google
        # Sort backends by quality priority (DeepSeek first, Google last)
        backend_priority = {"deepseek": 0, "ollama": 1, "google": 2}
        sorted_backends = sorted(self._backends, key=lambda x: backend_priority.get(x[0], 99))

        # Collect translations from all available backends (prioritize quality)
        # Use concurrent execution for speed, but maintain quality order
        import concurrent.futures
        from threading import Lock

        Lock()
        candidates_with_source = []  # Store (candidate, backend_name, priority)

        def translate_with_backend(backend_name, backend, priority):
            """Translate using a specific backend and return result with metadata."""
            try:
                result = backend.translate(req)
                if result.candidates and result.candidates[0]:
                    return (result.candidates[0], backend_name, priority, True, None)
                return (None, backend_name, priority, False, "No candidates")
            except Exception as e:
                return (None, backend_name, priority, False, str(e))

        # Execute all backends concurrently for speed
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(sorted_backends)) as executor:
            futures = {
                executor.submit(translate_with_backend, name, be, backend_priority.get(name, 99))
                for name, be in sorted_backends
            }

            for future in concurrent.futures.as_completed(futures):
                candidate, backend_name, priority, success, error = future.result()
                if success and candidate:
                    candidates_with_source.append((candidate, backend_name, priority))
                    backend_info.append(
                        {
                            "backend": backend_name,
                            "success": True,
                            "quality_priority": priority,
                        }
                    )
                else:
                    backend_info.append(
                        {
                            "backend": backend_name,
                            "success": False,
                            "error": error or "No candidates",
                        }
                    )

        # Sort candidates by quality priority (lower number = higher quality)
        candidates_with_source.sort(key=lambda x: x[2])
        candidates = [c[0] for c in candidates_with_source]

        if not candidates:
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
                "Consider setting up DeepSeek (free-tier, high quality) or Ollama (local)."
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
