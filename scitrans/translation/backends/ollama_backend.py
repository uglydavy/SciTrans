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
        prompt = (
            f"{req.system_prompt}\n\n"
            f"TRANSLATE THE FOLLOWING TEXT FROM {req.source_lang.upper()} TO {req.target_lang.upper()}:\n\n"
            f"{req.text}\n\n"
            f"Output ONLY the translated text in {req.target_lang.upper()}, preserving all placeholders."
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "temperature": req.temperature,
            "stream": False,
        }
        try:
            response = requests.post(url, json=payload, timeout=120)
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
