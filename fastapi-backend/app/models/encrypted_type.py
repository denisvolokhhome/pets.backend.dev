"""SQLAlchemy TypeDecorator for transparent field-level encryption.

Wraps AES-256-GCM encrypt/decrypt from the encryption service so that
sensitive string columns are encrypted on write and decrypted on read
without any changes to the calling code.
"""

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.services.encryption_service import decrypt, encrypt


class EncryptedString(TypeDecorator):
    """A string column that is transparently encrypted at rest.

    The underlying database column is ``String(512)`` to accommodate
    the base64-encoded ciphertext produced by AES-256-GCM encryption
    (nonce + ciphertext + auth tag).
    """

    impl = String(512)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Encrypt the value before storing it in the database."""
        if value is not None:
            return encrypt(value)
        return value

    def process_result_value(self, value, dialect):
        """Decrypt the value when reading it from the database."""
        if value is not None:
            return decrypt(value)
        return value
