from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def make_cache_key(
    backend: str,
    model: str,
    masked_text: str,
    source_lang: str,
    target_lang: str,
    prompt_version: str = "v1",
) -> str:
    """Generate a deterministic cache key for translation requests.

    This enables fast re-runs on the same document.
    """
    components = [
        backend,
        model,
        masked_text,
        source_lang,
        target_lang,
        prompt_version,
    ]
    combined = "|".join(str(c) for c in components)
    key_hash = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return f"cache_{key_hash[:16]}"


class TranslationCache:
    """Simple file-based cache for translations.

    Cache structure:
        cache_dir/
            {cache_key}.json -> {"candidates": [...], "meta": {...}}
    """

    def __init__(self, cache_dir: str | Path = "outputs/.cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(
        self,
        cache_key: str,
        *,
        max_age_seconds: int | None = None,
        expected_version: str | None = None,
    ) -> dict | None:
        """Retrieve cached translation result with TTL and version checks."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if expected_version and data.get("version") != expected_version:
                return None
            if max_age_seconds is not None:
                created_at = data.get("created_at")
                if not created_at:
                    return None
                if time.time() - float(created_at) > max_age_seconds:
                    return None
            return data
        except Exception:
            return None

    def get_with_status(
        self,
        cache_key: str,
        *,
        max_age_seconds: int | None = None,
        expected_version: str | None = None,
    ) -> tuple[dict | None, str]:
        """Retrieve cached result and a status string."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None, "miss_not_found"

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if expected_version and data.get("version") != expected_version:
                return None, "miss_version"
            if max_age_seconds is not None:
                created_at = data.get("created_at")
                if not created_at:
                    return None, "miss_no_timestamp"
                if time.time() - float(created_at) > max_age_seconds:
                    return None, "miss_expired"
            return data, "hit"
        except Exception:
            return None, "miss_error"

    def set(
        self,
        cache_key: str,
        candidates: list[str],
        meta: dict,
        *,
        version: str | None = None,
        created_at: float | None = None,
    ) -> None:
        """Store translation result in cache."""
        cache_file = self.cache_dir / f"{cache_key}.json"
        data = {
            "candidates": candidates,
            "meta": meta,
            "created_at": created_at or time.time(),
            "version": version,
        }
        cache_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> None:
        """Clear all cached entries."""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
