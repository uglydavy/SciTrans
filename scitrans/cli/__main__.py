"""Entry point for running scitrans CLI as a module.

This allows running as: python -m scitrans.cli
And prevents the RuntimeWarning about module import order.
"""

from scitrans.cli.main import app

if __name__ == "__main__":
    app()

