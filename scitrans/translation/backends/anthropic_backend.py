from __future__ import annotations

import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult
from scitrans.translation.backends.config import get_backend_config, get_backend_value


class AnthropicBackend:
    """Anthropic backend (Claude).

    Env vars:
      - ANTHROPIC_API_KEY (required)
      - ANTHROPIC_BASE_URL (optional proxy endpoint)
    """

    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ImportError(
                "anthropic SDK not installed. Install with: pip install anthropic"
            ) from e

        cfg = get_backend_config("anthropic")
        if model == "claude-3-5-sonnet-20241022" and cfg.get("model"):
            model = cfg.get("model")
        self.model = model
        self.api_key = (
            api_key
            or cfg.get("api_key")
            or get_backend_value("anthropic", "api_key", env_var="ANTHROPIC_API_KEY")
            or get_backend_value("anthropic", "auth_token", env_var="ANTHROPIC_AUTH_TOKEN")
        )
        if not self.api_key:
            raise ValueError("Missing Anthropic API key (configure .scitrans_backends.json)")

        base_url = (
            base_url
            or cfg.get("base_url")
            or get_backend_value("anthropic", "base_url", env_var="ANTHROPIC_BASE_URL")
            or get_backend_value("anthropic", "api_base_url", env_var="ANTHROPIC_API_BASE_URL")
        )
        kwargs = {"api_key": self.api_key}
        if base_url:
            # Anthropic SDK expects base_url without trailing /v1
            base_url = base_url.rstrip("/")
            if base_url.endswith("/v1"):
                base_url = base_url[:-3]
            kwargs["base_url"] = base_url

        self._client = Anthropic(**kwargs)

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
            # Context as separate message (reference only, do not translate)
            user_content = f"CONTEXT (for reference only, DO NOT translate):\n{context_text}\n\n---\n\nTRANSLATE THIS:\n{req.text}"
        else:
            user_content = req.text
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=req.temperature,
                system=req.system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
        except Exception:
            raise

        text = resp.content[0].text if resp.content else ""
        latency = time.time() - start
        return TranslateResult(
            candidates=[text.strip()],
            model=self.model,
            backend=self.name,
            meta={"latency_s": latency, "stop_reason": getattr(resp, "stop_reason", None)},
        )
