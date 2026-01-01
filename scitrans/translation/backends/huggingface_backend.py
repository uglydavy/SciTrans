from __future__ import annotations

import os
import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


class HuggingFaceBackend:
    """HuggingFace Inference API backend.

    Supports both:
    1. HuggingFace Inference API (free tier with rate limits)
    2. HuggingFace Inference Endpoints (paid, faster)

    Env vars:
      - HUGGINGFACE_API_KEY (optional for free tier, required for endpoints)
      - HUGGINGFACE_API_URL (optional, for custom endpoints)
    """

    name = "huggingface"

    def __init__(
        self,
        model: str = "Helsinki-NLP/opus-mt-en-fr",
        api_key: str | None = None,
        api_url: str | None = None,
    ):
        self.model = model
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY")
        self.api_url = api_url or os.getenv("HUGGINGFACE_API_URL")

        # If no custom URL, use standard Inference API
        if not self.api_url:
            self.api_url = f"https://api-inference.huggingface.co/models/{model}"

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        try:
            import requests  # type: ignore
        except Exception as e:
            raise ImportError("requests not installed. Install with: pip install requests") from e

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"inputs": req.text}
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            # HuggingFace returns list of dicts with "translation_text" key
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], dict) and "translation_text" in result[0]:
                    translated = result[0]["translation_text"]
                else:
                    translated = str(result[0])
            else:
                translated = ""

        except Exception:
            translated = ""

        latency = time.time() - start

        return TranslateResult(
            candidates=[translated],
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "api_url": self.api_url,
            },
        )
