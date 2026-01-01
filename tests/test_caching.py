"""Test translation caching."""

from pathlib import Path

from scitrans.translation.cache import TranslationCache, make_cache_key


def test_cache_key_deterministic():
    """Cache keys should be deterministic."""
    key1 = make_cache_key("anthropic", "claude", "Hello", "en", "fr")
    key2 = make_cache_key("anthropic", "claude", "Hello", "en", "fr")
    assert key1 == key2

    # Different text should produce different key
    key3 = make_cache_key("anthropic", "claude", "Goodbye", "en", "fr")
    assert key1 != key3


def test_cache_set_and_get(tmp_path: Path):
    """Cache should store and retrieve translations."""
    cache = TranslationCache(cache_dir=tmp_path / ".cache")

    cache_key = "test_key_123"
    candidates = ["Bonjour", "Salut"]
    meta = {"backend": "test", "model": "test-model"}

    # Set
    cache.set(cache_key, candidates, meta)

    # Get
    result = cache.get(cache_key)
    assert result is not None
    assert result["candidates"] == candidates
    assert result["meta"]["backend"] == "test"


def test_cache_miss(tmp_path: Path):
    """Cache miss should return None."""
    cache = TranslationCache(cache_dir=tmp_path / ".cache")
    result = cache.get("nonexistent_key")
    assert result is None


def test_cache_clear(tmp_path: Path):
    """Cache clear should remove all entries."""
    cache = TranslationCache(cache_dir=tmp_path / ".cache")

    # Add some entries
    cache.set("key1", ["Translation 1"], {})
    cache.set("key2", ["Translation 2"], {})

    # Clear
    cache.clear()

    # Both should be gone
    assert cache.get("key1") is None
    assert cache.get("key2") is None
