"""Test all translation backends."""

import os

import pytest

from scitrans.translation.backends.base import TranslateRequest
from scitrans.translation.backends.dummy import DummyBackend


def test_dummy_backend():
    """Dummy backend returns input as output."""
    backend = DummyBackend(model="test")
    req = TranslateRequest(
        text="Hello world",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate",
        temperature=0.0,
        n_candidates=1,
    )
    result = backend.translate(req)
    assert result.candidates == ["Hello world"]
    assert result.backend == "dummy"


def test_translate_request_validation():
    """TranslateRequest should accept valid inputs."""
    req = TranslateRequest(
        text="Test",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate professionally",
        temperature=0.5,
        n_candidates=3,
    )
    assert req.text == "Test"
    assert req.n_candidates == 3


# Backend-specific tests (skip if dependencies not installed)


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires ANTHROPIC_API_KEY")
def test_anthropic_backend():
    """Test Anthropic backend (requires API key)."""
    from scitrans.translation.backends.anthropic_backend import AnthropicBackend

    backend = AnthropicBackend(model="claude-3-5-sonnet-20241022")
    req = TranslateRequest(
        text="Hello world",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French",
    )
    result = backend.translate(req)
    assert len(result.candidates) > 0
    assert result.backend == "anthropic"
    # Should contain French translation
    assert result.candidates[0].strip() != "Hello world"


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OPENAI_API_KEY")
def test_openai_backend():
    """Test OpenAI backend (requires API key)."""
    from scitrans.translation.backends.openai_backend import OpenAIBackend

    backend = OpenAIBackend(model="gpt-4")
    req = TranslateRequest(
        text="Hello world",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French",
    )
    result = backend.translate(req)
    assert len(result.candidates) > 0
    assert result.backend == "openai"
    # Should contain French translation
    assert result.candidates[0].strip() != "Hello world"


@pytest.mark.skip(reason="Rate-limited, skip in CI")
def test_google_backend():
    """Test Google Translate backend (manual test, rate-limited)."""
    from scitrans.translation.backends.google_backend import GoogleTranslateBackend

    backend = GoogleTranslateBackend()
    req = TranslateRequest(
        text="Hello world",
        source_lang="en",
        target_lang="fr",
        system_prompt="",
    )
    result = backend.translate(req)
    assert len(result.candidates) > 0


def _is_ollama_running() -> bool:
    """Check if Ollama server is running."""
    try:
        import requests

        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


@pytest.mark.skipif(
    not _is_ollama_running(), reason="Requires Ollama running locally (ollama serve)"
)
def test_ollama_backend():
    """Test Ollama backend (requires local Ollama server)."""
    from scitrans.translation.backends.ollama_backend import OllamaBackend

    backend = OllamaBackend(model="llama2")  # Common default model
    req = TranslateRequest(
        text="Hello world",
        source_lang="en",
        target_lang="fr",
        system_prompt="Translate to French",
    )
    result = backend.translate(req)
    assert len(result.candidates) > 0
    assert result.backend == "ollama"
