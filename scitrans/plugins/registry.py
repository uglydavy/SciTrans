"""
Plugin Registry

Manages registration and discovery of plugins.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for SciTrans plugins."""

    def __init__(self):
        self.backends: dict[str, type] = {}
        self.renderers: dict[str, type] = {}
        self.scorers: dict[str, type] = {}
        self.maskers: dict[str, type] = {}

    def register_backend(self, name: str, backend_class: type):
        """Register a custom backend."""
        self.backends[name] = backend_class
        logger.info(f"Registered backend plugin: {name}")

    def register_renderer(self, name: str, renderer_class: type):
        """Register a custom renderer."""
        self.renderers[name] = renderer_class
        logger.info(f"Registered renderer plugin: {name}")

    def register_scorer(self, name: str, scorer_class: type):
        """Register a custom scorer."""
        self.scorers[name] = scorer_class
        logger.info(f"Registered scorer plugin: {name}")

    def register_masker(self, name: str, masker_class: type):
        """Register a custom masker."""
        self.maskers[name] = masker_class
        logger.info(f"Registered masker plugin: {name}")

    def get_backend(self, name: str) -> type | None:
        """Get registered backend by name."""
        return self.backends.get(name)

    def get_renderer(self, name: str) -> type | None:
        """Get registered renderer by name."""
        return self.renderers.get(name)

    def get_scorer(self, name: str) -> type | None:
        """Get registered scorer by name."""
        return self.scorers.get(name)

    def get_masker(self, name: str) -> type | None:
        """Get registered masker by name."""
        return self.maskers.get(name)

    def list_plugins(self) -> dict[str, list[str]]:
        """List all registered plugins."""
        return {
            "backends": list(self.backends.keys()),
            "renderers": list(self.renderers.keys()),
            "scorers": list(self.scorers.keys()),
            "maskers": list(self.maskers.keys()),
        }
