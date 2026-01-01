"""
Plugin System for SciTrans

Allows custom backends, renderers, and scorers to be registered.
"""

from scitrans.plugins.registry import PluginRegistry

__all__ = ["PluginRegistry"]

# Global plugin registry
registry = PluginRegistry()
