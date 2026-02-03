from __future__ import annotations

import logging
import time

from scitrans.translation.backends.config import get_backend_config, get_backend_value

from scitrans.translation.backends.base import TranslateRequest, TranslateResult

logger = logging.getLogger(__name__)


class GoogleTranslateBackend:
    """Google Translate backend (free tier via googletrans library).

    No API key required, but rate-limited and less reliable than paid APIs.
    Best for testing or low-volume use.

    Note: Uses unofficial googletrans library (free but may break).
    """

    name = "google_free"

    def __init__(self, model: str = "google-translate"):
        self.model = model
        self._translator = None
        self._use_deep_translator = False

        # Try deep-translator first (more stable, no dependency conflicts)
        try:
            from deep_translator import GoogleTranslator  # type: ignore

            self._translator = GoogleTranslator(source='auto', target='en')
            self._use_deep_translator = True
        except ImportError:
            # Fallback to googletrans (may have httpx compatibility issues)
            try:
                from googletrans import Translator  # type: ignore

                self._translator = Translator()
            except (ImportError, AttributeError) as e:
                raise ImportError(
                    "Neither deep-translator nor googletrans is installed. "
                    "Install with: pip install deep-translator>=1.11.0 "
                    "OR pip install googletrans==4.0.0rc1 (may cause conflicts)"
                ) from e

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()
        # Keep 3 retries for reliability (Google Translate has network issues)
        max_retries = 3
        translated = None
        last_error = None

        for attempt in range(max_retries):
            try:
                # Use threading timeout for cross-platform support (60 seconds max)
                import threading
                translated_result = [None]
                exception_result = [None]
                
                def translate_worker():
                    try:
                        if self._use_deep_translator:
                            # deep-translator API - need to recreate with correct language pair
                            from deep_translator import GoogleTranslator
                            translator = GoogleTranslator(source=req.source_lang, target=req.target_lang)
                            result = translator.translate(req.text)
                            # Validate non-empty result
                            if result and result.strip():
                                translated_result[0] = result
                            else:
                                raise ValueError(f"Empty translation returned (attempt {attempt+1})")
                        else:
                            # googletrans API
                            result = self._translator.translate(
                                req.text,
                                src=req.source_lang,
                                dest=req.target_lang,
                            )
                            # Validate non-empty result
                            if result and result.text and result.text.strip():
                                translated_result[0] = result.text
                            else:
                                raise ValueError(f"Empty translation returned (attempt {attempt+1})")
                    except Exception as e:
                        exception_result[0] = e
                
                # Use timeout from request if available, otherwise default to 60s
                request_timeout = getattr(req, 'timeout', 60.0) if hasattr(req, 'timeout') else 60.0
                # Ensure minimum timeout of 30s for safety
                thread_timeout = max(30.0, request_timeout)
                
                thread = threading.Thread(target=translate_worker, daemon=True)
                thread.start()
                thread.join(timeout=thread_timeout)
                
                if thread.is_alive():
                    # Timeout - retry
                    raise TimeoutError(f"Translation timeout after {thread_timeout:.0f}s (attempt {attempt+1})")
                elif exception_result[0]:
                    raise exception_result[0]
                elif translated_result[0]:
                    translated = translated_result[0]
                    # Success - break retry loop
                    if attempt > 0:
                        logger.info(f"Google Translate retry #{attempt} successful")
                    break
                else:
                    raise ValueError(f"No translation returned (attempt {attempt+1})")
                    
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Google Translate error (attempt {attempt+1}/{max_retries}): {str(e)[:100]} - retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"Google Translate failed after {max_retries} attempts: {str(e)[:100]}")
                    # Return None to indicate failure (not empty string)
                    translated = None

        latency = time.time() - start

        # Return result with empty list if failed (not [""])
        return TranslateResult(
            candidates=[translated] if translated else [],
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "note": "Free tier, rate-limited, may be unreliable",
                "provider": "deep-translator" if self._use_deep_translator else "googletrans",
                "error": str(last_error)[:200] if last_error and not translated else None,
                "attempts": max_retries if not translated else attempt + 1,
            },
        )


class GoogleAIBackend:
    """Google AI (Gemini) backend.

    Config file:
      - google_ai.api_key (required)
      - google_ai.base_url (optional)
      - google_ai.model (optional)
    """

    name = "google_ai"

    def __init__(
        self,
        model: str = "gemini-1.5-flash",
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        cfg = get_backend_config("google_ai")
        self.api_key = api_key or cfg.get("api_key") or get_backend_value("google_ai", "api_key")
        if not self.api_key:
            raise ValueError("Missing Google AI API key (configure .scitrans_backends.json)")
        self.base_url = base_url or cfg.get("base_url") or "https://generativelanguage.googleapis.com/v1beta"
        if model == "gemini-1.5-flash" and cfg.get("model"):
            model = cfg.get("model")
        self.model = model

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()
        try:
            import requests  # type: ignore
        except Exception as e:
            raise ImportError("requests not installed. Install with: pip install requests") from e

        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "system_instruction": {"parts": [{"text": req.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": req.text}]}],
            "generationConfig": {
                "temperature": req.temperature,
                "candidateCount": req.n_candidates,
            },
        }
        candidates: list[str] = []
        error = None
        try:
            response = requests.post(url, json=payload, timeout=req.timeout)
            response.raise_for_status()
            data = response.json()
            for cand in data.get("candidates", []):
                content = cand.get("content", {})
                parts = content.get("parts", [])
                text = "".join(p.get("text", "") for p in parts if p.get("text"))
                if text.strip():
                    candidates.append(text.strip())
        except Exception as e:
            error = str(e)

        latency = time.time() - start
        return TranslateResult(
            candidates=candidates if candidates else [""],
            model=self.model,
            backend=self.name,
            meta={"latency_s": latency, "error": error},
        )
