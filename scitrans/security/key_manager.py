"""
Secure API Key Management

Provides secure storage and retrieval of API keys.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet

    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False
    logger.warning(
        "cryptography not available. Using plaintext storage (not recommended for production)."
    )


class KeyManager:
    """Manages API keys securely."""

    def __init__(self, key_file: Path | str = ".scitrans_keys"):
        self.key_file = Path(key_file)
        self.keys: dict[str, str] = {}
        self._cipher: Fernet | None = None

        if CRYPTO_AVAILABLE:
            self._init_encryption()

        self.load_keys()

    def _init_encryption(self) -> None:
        """Initialize encryption for key storage."""
        key_file = Path(".scitrans_encryption_key")

        if key_file.exists():
            key = key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            key_file.chmod(0o600)  # Read/write for owner only

        self._cipher = Fernet(key)

    def _encrypt(self, value: str) -> str:
        """Encrypt a value."""
        if self._cipher:
            return self._cipher.encrypt(value.encode()).decode()
        # Fallback: base64 encoding (not secure, but better than plaintext)
        return base64.b64encode(value.encode()).decode()

    def _decrypt(self, value: str) -> str:
        """Decrypt a value."""
        if self._cipher:
            return self._cipher.decrypt(value.encode()).decode()
        # Fallback: base64 decoding
        return base64.b64decode(value.encode()).decode()

    def set_key(self, backend: str, api_key: str) -> None:
        """Store an API key securely."""
        self.keys[backend] = self._encrypt(api_key)
        self.save_keys()
        logger.info(f"API key stored for backend: {backend}")

    def get_key(self, backend: str) -> str | None:
        """Retrieve an API key."""
        encrypted = self.keys.get(backend)
        if encrypted:
            try:
                return self._decrypt(encrypted)
            except Exception as e:
                logger.error(f"Failed to decrypt key for {backend}: {e}")
                return None
        return None

    def load_keys(self) -> None:
        """Load keys from file."""
        if not self.key_file.exists():
            return

        try:
            import json

            data = json.loads(self.key_file.read_text())
            self.keys = data
            logger.debug(f"Loaded {len(self.keys)} API keys")
        except Exception as e:
            logger.error(f"Failed to load keys: {e}")

    def save_keys(self) -> None:
        """Save keys to file."""
        try:
            import json

            self.key_file.parent.mkdir(parents=True, exist_ok=True)
            self.key_file.write_text(json.dumps(self.keys, indent=2))
            self.key_file.chmod(0o600)  # Read/write for owner only
            logger.debug("API keys saved")
        except Exception as e:
            logger.error(f"Failed to save keys: {e}")

    def delete_key(self, backend: str) -> None:
        """Delete an API key."""
        if backend in self.keys:
            del self.keys[backend]
            self.save_keys()
            logger.info(f"API key deleted for backend: {backend}")
