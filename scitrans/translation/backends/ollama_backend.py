from __future__ import annotations

import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult
from scitrans.translation.backends.config import get_backend_config, get_backend_value


class OllamaBackend:
    """Ollama backend for local LLM translation.

    Requires Ollama to be installed and running locally.
    Install: https://ollama.ai/

    Config file:
      - ollama.host (optional, default: http://localhost:11434)
      - ollama.api_key (optional)
    """

    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.2",
        host: str | None = None,
        api_key: str | None = None,
    ):
        cfg = get_backend_config("ollama")
        if model == "llama3.2" and cfg.get("model"):
            model = cfg.get("model")
        self.model = model
        self.host = host or cfg.get("host") or get_backend_value("ollama", "host", env_var="OLLAMA_HOST") or "http://localhost:11434"
        self.api_key = api_key or cfg.get("api_key") or get_backend_value("ollama", "api_key", env_var="OLLAMA_API_KEY")

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
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = requests.post(url, json=payload, timeout=request_timeout, headers=headers or None)
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
