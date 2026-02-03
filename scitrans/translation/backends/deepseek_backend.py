from __future__ import annotations

import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult
from scitrans.translation.backends.config import get_backend_config, get_backend_value


class DeepSeekBackend:
    """DeepSeek backend for translation.

    DeepSeek models are OpenAI-compatible and provide high-quality translation.

    Config file:
      - deepseek.api_key (required)
      - deepseek.base_url (optional, default: https://api.deepseek.com)
    """

    name = "deepseek"

    def __init__(
        self,
        model: str = "deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ImportError("openai SDK not installed. Install with: pip install openai") from e

        self.model = model
        if api_key is None:
            cfg = get_backend_config("deepseek")
            api_key = cfg.get("api_key") or get_backend_value("deepseek", "api_key", env_var="DEEPSEEK_API_KEY")
            base_url = base_url or cfg.get("base_url")
            if model == "deepseek-chat" and cfg.get("model"):
                model = cfg.get("model")
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("Missing DeepSeek API key (configure .scitrans_backends.json)")

        self.base_url = base_url or "https://api.deepseek.com"
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        # Build messages
        messages = [
            {"role": "system", "content": req.system_prompt},
        ]

        # Add context if provided (separate message, not translated)
        # Context is now a dict, but we support legacy string context for backward compatibility
        context_text = None
        if isinstance(req.context, dict):
            # Extract text context if present, otherwise ignore dict context (it's metadata)
            context_text = req.context.get("text") if req.context else None
        elif isinstance(req.context, str) and req.context:
            # Legacy string context
            context_text = req.context
        
        if context_text:
            messages.append(
                {
                    "role": "system",
                    "content": f"Reference context (do NOT translate):\n{context_text}",
                }
            )

        messages.append({"role": "user", "content": req.text})

        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                n=req.n_candidates,
                temperature=req.temperature,
            )

            candidates = [
                choice.message.content.strip()
                for choice in resp.choices
                if choice.message and choice.message.content
            ]
            latency = time.time() - start

            return TranslateResult(
                candidates=candidates if candidates else [""],
                model=self.model,
                backend=self.name,
                meta={
                    "latency_s": latency,
                    "finish_reason": resp.choices[0].finish_reason if resp.choices else None,
                },
            )
        except Exception as e:
            # Return empty result with error info instead of crashing
            latency = time.time() - start
            return TranslateResult(
                candidates=[""],
                model=self.model,
                backend=self.name,
                meta={"latency_s": latency, "error": str(e)},
            )
