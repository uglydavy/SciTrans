from __future__ import annotations

import os
import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


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

        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Missing OPENAI_API_KEY")

        kwargs = {"api_key": self.api_key}

        base_url = base_url or os.getenv("OPENAI_BASE_URL")
        if base_url:
            kwargs["base_url"] = base_url

        org_id = org_id or os.getenv("OPENAI_ORG_ID")
        if org_id:
            kwargs["organization"] = org_id

        self._client = OpenAI(**kwargs)

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        # Build messages with context if provided
        if req.context:
            user_content = f"CONTEXT (for reference only, DO NOT translate):\n{req.context}\n\n---\n\nTRANSLATE THIS:\n{req.text}"
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
