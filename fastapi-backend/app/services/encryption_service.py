"""AES-256-GCM encryption service for sensitive billing data.

Provides encrypt/decrypt functions using a key derived from the
BILLING_ENCRYPTION_KEY environment variable via PBKDF2.
Each encryption generates a random 12-byte nonce prepended to the
ciphertext; the combined output is base64-encoded.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import Settings

# Static salt for deterministic key derivation from the same passphrase.
_STATIC_SALT = b"breedly-billing-encryption-salt-v1"

_NONCE_LENGTH = 12  # 96-bit nonce recommended for AES-GCM


def _derive_key(passphrase: str) -> bytes:
    """Derive a 256-bit key from *passphrase* using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_STATIC_SALT,
        iterations=480_000,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _get_key() -> bytes:
    """Return the derived encryption key from application settings."""
    settings = Settings()
    key_material = settings.billing_encryption_key
    if not key_material:
        raise ValueError(
            "BILLING_ENCRYPTION_KEY environment variable is not set. "
            "Field-level encryption requires a non-empty key."
        )
    return _derive_key(key_material)


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* with AES-256-GCM.

    Returns a base64-encoded string containing the 12-byte nonce
    followed by the ciphertext + GCM authentication tag.

    Raises ``ValueError`` if *plaintext* is ``None`` or empty.
    """
    if plaintext is None:
        raise ValueError("Cannot encrypt None value")
    if plaintext == "":
        raise ValueError("Cannot encrypt empty string")

    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded *ciphertext* produced by :func:`encrypt`.

    Returns the original plaintext string.

    Raises ``ValueError`` if *ciphertext* is ``None`` or empty.
    """
    if ciphertext is None:
        raise ValueError("Cannot decrypt None value")
    if ciphertext == "":
        raise ValueError("Cannot decrypt empty string")

    key = _get_key()
    raw = base64.b64decode(ciphertext)
    nonce = raw[:_NONCE_LENGTH]
    encrypted_data = raw[_NONCE_LENGTH:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, encrypted_data, None).decode("utf-8")
