"""Translation backends for SciTrans."""

from scitrans.translation.backends.anthropic_backend import AnthropicBackend
from scitrans.translation.backends.cascade_free import CascadeFreeBackend
from scitrans.translation.backends.deepseek_backend import DeepSeekBackend
from scitrans.translation.backends.dummy import DummyBackend
from scitrans.translation.backends.google_backend import GoogleTranslateBackend
from scitrans.translation.backends.huggingface_backend import HuggingFaceBackend
from scitrans.translation.backends.ollama_backend import OllamaBackend
from scitrans.translation.backends.openai_backend import OpenAIBackend

__all__ = [
    "AnthropicBackend",
    "CascadeFreeBackend",
    "DeepSeekBackend",
    "DummyBackend",
    "GoogleTranslateBackend",
    "HuggingFaceBackend",
    "OllamaBackend",
    "OpenAIBackend",
]

