from __future__ import annotations

import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult
from scitrans.translation.backends.config import get_backend_config, get_backend_value


class OpenAIBackend:
    """OpenAI-compatible backend (OpenAI, Cascade, TogetherAI, etc.).

    Env vars:
      - OPENAI_API_KEY (required)
      - OPENAI_BASE_URL (optional, for OpenAI-compatible gateways)
      - OPENAI_ORG_ID (optional)
    """

    name = "openai"

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        org_id: str | None = None,
    ):
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:
            raise ImportError("openai SDK not installed. Install with: pip install openai") from e

        cfg = get_backend_config("openai")
        if model == "gpt-4o" and cfg.get("model"):
            model = cfg.get("model")
        self.model = model
        self.api_key = api_key or cfg.get("api_key") or get_backend_value("openai", "api_key", env_var="OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Missing OpenAI API key (configure .scitrans_backends.json)")

        kwargs = {"api_key": self.api_key}

        base_url = base_url or cfg.get("base_url") or get_backend_value("openai", "base_url", env_var="OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

        org_id = org_id or cfg.get("org_id") or get_backend_value("openai", "org_id", env_var="OPENAI_ORG_ID")
        if org_id:
            kwargs["organization"] = org_id

        self._client = OpenAI(**kwargs)

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        # Build messages with context if provided
        # Context is now a dict, but we support legacy string context for backward compatibility
        context_text = None
        if isinstance(req.context, dict):
            # Extract text context if present, otherwise ignore dict context (it's metadata)
            context_text = req.context.get("text") if req.context else None
        elif isinstance(req.context, str) and req.context:
            # Legacy string context
            context_text = req.context
        
        if context_text:
            user_content = f"CONTEXT (for reference only, DO NOT translate):\n{context_text}\n\n---\n\nTRANSLATE THIS:\n{req.text}"
        else:
            user_content = req.text

        messages = [
            {"role": "system", "content": req.system_prompt},
            {"role": "user", "content": user_content},
        ]

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            n=req.n_candidates,
        )

        candidates = [
            choice.message.content.strip() for choice in resp.choices if choice.message.content
        ]
        latency = time.time() - start

        return TranslateResult(
            candidates=candidates,
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "finish_reason": resp.choices[0].finish_reason if resp.choices else None,
                "usage": resp.usage.model_dump() if resp.usage else None,
            },
        )
