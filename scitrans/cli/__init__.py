"""Command-line interface for SciTrans."""

# Don't import app here to avoid RuntimeWarning about module import order
# The entry point (scitrans.cli.main:app) imports it directly
__all__ = ["app"]

# Lazy import to avoid the RuntimeWarning
def __getattr__(name: str):
    """Lazy import to avoid RuntimeWarning about module import order."""
    if name == "app":
        from scitrans.cli.main import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

