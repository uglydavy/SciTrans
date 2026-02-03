"""Entry point for running scitrans CLI as a module.

This allows running as: python3 -m scitrans.cli or simply scitrans
And prevents the RuntimeWarning about module import order.
"""

from scitrans.cli.main import app

if __name__ == "__main__":
    app()

