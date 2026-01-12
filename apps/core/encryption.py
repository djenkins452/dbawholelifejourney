# ==============================================================================
# File: apps/core/encryption.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Centralized encryption utilities for OAuth tokens and sensitive data
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12 (CISO Security Review - Batch 1)
# Last Updated: 2026-01-12
# ==============================================================================
"""
Core Encryption Service

Provides Fernet-based encryption for OAuth tokens and other sensitive data.
Uses AES-256 encryption with authenticated encryption (AEAD).

This module provides encryption for:
    - Google Calendar OAuth tokens
    - Dexcom OAuth tokens
    - Any other sensitive credentials that need encryption at rest

Security:
    - Tokens are encrypted at rest using a key stored in environment
    - Key must be a 32-byte URL-safe base64-encoded string
    - Never log or expose decrypted tokens

Environment Variables:
    OAUTH_TOKEN_ENCRYPTION_KEY - Fernet encryption key for OAuth tokens

Generate a new key:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())

================================================================================
KEY ROTATION PROCEDURE
================================================================================

When to rotate the encryption key:
    1. Suspected key compromise
    2. After employee with access leaves the company
    3. Regularly (recommended: annually)
    4. After a security audit requires it

Key Rotation Steps:

    1. PREPARATION (scheduled maintenance window):
       - Generate a new Fernet key:
         >>> from cryptography.fernet import Fernet
         >>> new_key = Fernet.generate_key().decode()
         >>> print(new_key)

       - Store the new key securely (password manager, secrets vault)
       - Back up the current key (needed for step 2)

    2. RE-ENCRYPT ALL TOKENS (run in Django shell):

       ```python
       from cryptography.fernet import Fernet
       from apps.life.models import GoogleCalendarCredential
       from apps.health.models import DexcomCredential

       # Old and new keys
       OLD_KEY = 'your-old-key-here'
       NEW_KEY = 'your-new-key-here'

       old_fernet = Fernet(OLD_KEY.encode())
       new_fernet = Fernet(NEW_KEY.encode())

       # Re-encrypt Google Calendar tokens
       for cred in GoogleCalendarCredential.objects.all():
           for field in ['access_token', 'refresh_token', 'client_secret']:
               value = getattr(cred, field)
               if value and not value.startswith('UNENCRYPTED:'):
                   try:
                       decrypted = old_fernet.decrypt(value.encode()).decode()
                       setattr(cred, field, new_fernet.encrypt(decrypted.encode()).decode())
                   except Exception as e:
                       print(f"ERROR: GoogleCalendarCredential {cred.id} {field}: {e}")
           cred.save()

       # Re-encrypt Dexcom tokens
       for cred in DexcomCredential.objects.all():
           for field in ['access_token', 'refresh_token']:
               value = getattr(cred, field)
               if value and not value.startswith('UNENCRYPTED:'):
                   try:
                       decrypted = old_fernet.decrypt(value.encode()).decode()
                       setattr(cred, field, new_fernet.encrypt(decrypted.encode()).decode())
                   except Exception as e:
                       print(f"ERROR: DexcomCredential {cred.id} {field}: {e}")
           cred.save()
       ```

    3. UPDATE ENVIRONMENT VARIABLE:
       - In Railway dashboard: Update OAUTH_TOKEN_ENCRYPTION_KEY to new key
       - Redeploy the application

    4. VERIFY:
       - Test that existing OAuth connections still work
       - Check logs for any decryption errors

    5. CLEANUP:
       - Delete the old key from your records after 30 days
       - Document the rotation in changelog

================================================================================
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_oauth_fernet():
    """
    Get a Fernet instance using the configured OAuth encryption key.

    Returns:
        Fernet instance or None if not configured

    Raises:
        ValueError: If key is invalid
    """
    key = getattr(settings, 'OAUTH_TOKEN_ENCRYPTION_KEY', None)

    if not key:
        logger.warning(
            "OAUTH_TOKEN_ENCRYPTION_KEY not configured. "
            "OAuth token encryption is disabled."
        )
        return None

    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.error(f"Invalid OAUTH_TOKEN_ENCRYPTION_KEY: {e}")
        raise ValueError(
            "OAUTH_TOKEN_ENCRYPTION_KEY is invalid. "
            "Generate a new key with: Fernet.generate_key()"
        )


def encrypt_oauth_token(plaintext: str) -> str:
    """
    Encrypt an OAuth token for secure database storage.

    Args:
        plaintext: The token to encrypt

    Returns:
        Encrypted token as a string, or plaintext if encryption not configured

    Note:
        If encryption is not configured (no key), returns plaintext with a
        warning logged. This allows development without encryption but
        should never be used in production.
    """
    if not plaintext:
        return ''

    fernet = get_oauth_fernet()

    if fernet is None:
        # Development fallback - NOT for production
        logger.warning("Storing OAuth token WITHOUT encryption (dev mode only)")
        return f"UNENCRYPTED:{plaintext}"

    try:
        encrypted = fernet.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as e:
        logger.error(f"OAuth token encryption failed: {e}")
        raise


def decrypt_oauth_token(ciphertext: str) -> str:
    """
    Decrypt an OAuth token retrieved from the database.

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
        logger.warning("Reading unencrypted OAuth token (dev mode only)")
        return ciphertext[12:]  # Remove prefix

    fernet = get_oauth_fernet()

    if fernet is None:
        raise ValueError(
            "Cannot decrypt token: OAUTH_TOKEN_ENCRYPTION_KEY not configured"
        )

    try:
        decrypted = fernet.decrypt(ciphertext.encode())
        return decrypted.decode()
    except Exception as e:
        logger.error(f"OAuth token decryption failed: {e}")
        raise ValueError("OAuth token decryption failed. Key may have changed.")


def generate_oauth_encryption_key() -> str:
    """
    Generate a new Fernet encryption key for OAuth tokens.

    Returns:
        A new 32-byte URL-safe base64-encoded key string

    Usage:
        Run this once to generate a key for your environment:
        >>> from apps.core.encryption import generate_oauth_encryption_key
        >>> print(generate_oauth_encryption_key())
        # Add the output to your .env as OAUTH_TOKEN_ENCRYPTION_KEY
    """
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
