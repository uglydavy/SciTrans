from __future__ import annotations

import time

from scitrans.translation.backends.base import TranslateRequest, TranslateResult


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

        # Try googletrans first
        try:
            from googletrans import Translator  # type: ignore

            self._translator = Translator()
        except (ImportError, AttributeError) as e:
            # googletrans has known issues with httpcore compatibility
            # Try deep-translator as fallback
            try:
                from deep_translator import GoogleTranslator  # type: ignore

                self._translator = GoogleTranslator()
                self._use_deep_translator = True
            except ImportError:
                raise ImportError(
                    "Neither googletrans nor deep-translator is installed. "
                    "Install with: pip install googletrans==4.0.0rc1 "
                    "OR pip install deep-translator>=1.11.0"
                ) from e

    def translate(self, req: TranslateRequest) -> TranslateResult:
        start = time.time()

        try:
            # Use threading timeout for cross-platform support (30 seconds max)
            import threading
            translated_result = [None]
            exception_result = [None]
            
            def translate_worker():
                try:
                    if self._use_deep_translator:
                        # deep-translator API
                        translated_result[0] = self._translator.translate(
                            req.text,
                            source=req.source_lang,
                            target=req.target_lang,
                        )
                    else:
                        # googletrans API
                        result = self._translator.translate(
                            req.text,
                            src=req.source_lang,
                            dest=req.target_lang,
                        )
                        translated_result[0] = result.text if result and result.text else ""
                except Exception as e:
                    exception_result[0] = e
            
            thread = threading.Thread(target=translate_worker, daemon=True)
            thread.start()
            thread.join(timeout=30.0)  # 30 second timeout
            
            if thread.is_alive():
                # Timeout - return empty
                translated = ""
            elif exception_result[0]:
                raise exception_result[0]
            else:
                translated = translated_result[0] if translated_result[0] else ""
        except Exception as e:
            # Fallback: return empty on error
            translated = ""
            f"Translation error: {str(e)}"

        latency = time.time() - start

        return TranslateResult(
            candidates=[translated],
            model=self.model,
            backend=self.name,
            meta={
                "latency_s": latency,
                "note": "Free tier, rate-limited, may be unreliable",
                "provider": "deep-translator" if self._use_deep_translator else "googletrans",
            },
        )
