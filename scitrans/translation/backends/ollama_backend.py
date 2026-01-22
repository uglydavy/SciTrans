from __future__ import annotations

import os
import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


class OllamaBackend:
    """Ollama backend for local LLM translation.

    Requires Ollama to be installed and running locally.
    Install: https://ollama.ai/

    Env vars:
      - OLLAMA_HOST (optional, default: http://localhost:11434)
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2",
        host: str | None = None,
    ):
        self.model = model
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        try:
            import requests  # type: ignore
        except Exception as e:
            raise ImportError("requests not installed. Install with: pip install requests") from e

        # Ollama API endpoint
        url = f"{self.host}/api/generate"

        # Combine system prompt and user text
        # Make it very clear this is a translation task
        # CRITICAL: Emphasize placeholder preservation but DO NOT include instructions that will be echoed
        # The system prompt already has all instructions - we just need to make the task clear
        prompt = (
            f"{req.system_prompt}\n\n"
            f"TRANSLATE THE FOLLOWING TEXT FROM {req.source_lang.upper()} TO {req.target_lang.upper()}:\n\n"
            f"{req.text}\n\n"
            f"Remember: Output ONLY the translated text. Do not include any instructions, explanations, or labels."
        )

        # PHASE 3.3: Optimize Ollama for speed
        # Use timeout from request if available, otherwise default to 120s
        request_timeout = getattr(req, 'timeout', 120.0) if hasattr(req, 'timeout') else 120.0
        # Ensure minimum timeout of 60s for safety
        request_timeout = max(60.0, request_timeout)
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": req.temperature,
                "num_predict": 512,  # Limit output length to prevent over-generation
                "num_ctx": 1024,     # Reduce context window (was default 2048) for faster processing
                "top_p": 0.9,        # Nucleus sampling for quality
            },
        }
        try:
            response = requests.post(url, json=payload, timeout=request_timeout)
            response.raise_for_status()
            result = response.json()
            # Ollama returns {"response": "..."}
            translated = result.get("response", "").strip()

        except Exception:
            translated = ""

        latency = time.time() - start

        return TranslateResult(
            candidates=[translated],
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "host": self.host,
                "note": "Local Ollama instance",
            },
        )
