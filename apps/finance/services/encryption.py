# ==============================================================================
# File: apps/finance/services/encryption.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Token encryption utilities for secure bank credential storage
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Token Encryption Service

Provides Fernet-based encryption for Plaid access tokens.
Uses AES-256 encryption with authenticated encryption (AEAD).

Security:
    - Tokens are encrypted at rest using a key stored in environment
    - Key must be a 32-byte URL-safe base64-encoded string
    - Never log or expose decrypted tokens

Environment Variables:
    BANK_TOKEN_ENCRYPTION_KEY - Fernet encryption key

Generate a new key:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_fernet():
    """
    Get a Fernet instance using the configured encryption key.

    Returns:
        Fernet instance or None if not configured

    Raises:
        ValueError: If key is invalid
    """
    key = getattr(settings, 'BANK_TOKEN_ENCRYPTION_KEY', None)

    if not key:
        logger.warning(
            "BANK_TOKEN_ENCRYPTION_KEY not configured. "
            "Bank token encryption is disabled."
        )
        return None

    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f"Invalid BANK_TOKEN_ENCRYPTION_KEY: {e}")
        raise ValueError(
            "BANK_TOKEN_ENCRYPTION_KEY is invalid. "
            "Generate a new key with: Fernet.generate_key()"
        )


def encrypt_token(plaintext: str) -> str:
    """
    Encrypt a token for secure database storage.

    Args:
        plaintext: The access token to encrypt

    Returns:
        Encrypted token as a string, or plaintext if encryption not configured

    Note:
        If encryption is not configured (no key), returns plaintext with a
        warning logged. This allows development without encryption but
        should never be used in production.
    """
    if not plaintext:
        return ''

    fernet = get_fernet()

    if fernet is None:
        # Development fallback - NOT for production
        logger.warning("Storing token WITHOUT encryption (dev mode only)")
        return f"UNENCRYPTED:{plaintext}"

    try:
        encrypted = fernet.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"Token encryption failed: {e}")
        raise


def decrypt_token(ciphertext: str) -> str:
    """
    Decrypt a token retrieved from the database.

    Args:
        ciphertext: The encrypted token string

    Returns:
        Decrypted plaintext token

    Raises:
        ValueError: If decryption fails (invalid key or corrupted data)
    """
    if not ciphertext:
        return ''

    # Handle unencrypted development tokens
    if ciphertext.startswith('UNENCRYPTED:'):
        logger.warning("Reading unencrypted token (dev mode only)")
        return ciphertext[12:]  # Remove prefix

    fernet = get_fernet()

    if fernet is None:
        raise ValueError(
            "Cannot decrypt token: BANK_TOKEN_ENCRYPTION_KEY not configured"
        )

    try:
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Token decryption failed: {e}")
        raise ValueError("Token decryption failed. Key may have changed.")


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        A new 32-byte URL-safe base64-encoded key string

    Usage:
        Run this once to generate a key for your environment:
        >>> from apps.finance.services.encryption import generate_encryption_key
        >>> print(generate_encryption_key())
        # Add the output to your .env as BANK_TOKEN_ENCRYPTION_KEY
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
