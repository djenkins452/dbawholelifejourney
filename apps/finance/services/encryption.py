# ==============================================================================
# File: apps/finance/services/encryption.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Token encryption utilities for secure bank credential storage
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-03
# Last Updated: 2026-01-12 (CISO Review - Key Rotation Documentation)
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

================================================================================
KEY ROTATION PROCEDURE (CISO Review 2026-01-12)
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
       from apps.finance.models import BankConnection

       # Old and new keys
       OLD_KEY = 'your-old-key-here'
       NEW_KEY = 'your-new-key-here'

       old_fernet = Fernet(OLD_KEY.encode())
       new_fernet = Fernet(NEW_KEY.encode())

       # Re-encrypt each token
       connections = BankConnection.objects.all()
       for conn in connections:
           if conn.access_token and not conn.access_token.startswith('UNENCRYPTED:'):
               try:
                   # Decrypt with old key
                   decrypted = old_fernet.decrypt(conn.access_token.encode()).decode()
                   # Re-encrypt with new key
                   conn.access_token = new_fernet.encrypt(decrypted.encode()).decode()
                   conn.save(update_fields=['access_token'])
                   print(f"Re-encrypted token for BankConnection {conn.id}")
               except Exception as e:
                   print(f"ERROR: Failed to re-encrypt BankConnection {conn.id}: {e}")
       ```

    3. UPDATE ENVIRONMENT VARIABLE:
       - In Railway dashboard: Update BANK_TOKEN_ENCRYPTION_KEY to new key
       - Redeploy the application

    4. VERIFY:
       - Test that existing bank connections still work
       - Check logs for any decryption errors

    5. CLEANUP:
       - Delete the old key from your records after 30 days
       - Document the rotation in changelog

ROLLBACK PROCEDURE:
    If issues occur after updating the environment variable:
    1. Immediately revert BANK_TOKEN_ENCRYPTION_KEY to the old key
    2. Redeploy
    3. Investigate the issue before attempting rotation again

================================================================================
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


#: Legacy marker written by the removed development fallback. Tokens carrying it are
#: PLAINTEXT. Reading one still works — it may be the only credential that can revoke a
#: live provider Item, and destroying it would strand that access forever — but writing
#: one is now impossible.
LEGACY_PLAINTEXT_PREFIX = 'UNENCRYPTED:'


class EncryptionNotConfigured(RuntimeError):
    """Raised instead of silently storing a financial credential in plaintext."""


def get_fernet():
    """Return a Fernet instance, or raise. NEVER returns None.

    FAIL CLOSED: a missing or invalid key is a configuration failure, not a licence to
    store a bank credential in the clear.

    Raises:
        EncryptionNotConfigured: key absent or unusable.
    """
    key = getattr(settings, 'BANK_TOKEN_ENCRYPTION_KEY', None)

    if not key:
        raise EncryptionNotConfigured(
            "BANK_TOKEN_ENCRYPTION_KEY is not configured. Bank and provider tokens "
            "cannot be stored without encryption."
        )

    try:
        from cryptography.fernet import Fernet
        return Fernet(key.encode() if isinstance(key, str) else key)
    except EncryptionNotConfigured:
        raise
    except Exception as e:
        # The key itself is never logged, only that it failed to load.
        logger.error("BANK_TOKEN_ENCRYPTION_KEY is invalid: %s", type(e).__name__)
        raise EncryptionNotConfigured(
            "BANK_TOKEN_ENCRYPTION_KEY is invalid. "
            "Generate a new key with: Fernet.generate_key()"
        )


def encryption_available() -> bool:
    """Is token encryption usable right now? Used by config checks and health probes.

    Returns a boolean and NEVER the key, so it is safe to expose in an operator report.
    """
    try:
        get_fernet()
        return True
    except EncryptionNotConfigured:
        return False


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token for storage. Raises rather than storing it in the clear.

    Raises:
        EncryptionNotConfigured: no usable key — the caller must abort, not degrade.
    """
    if not plaintext:
        return ''

    fernet = get_fernet()          # raises when unusable; never returns None
    try:
        return fernet.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.error("Token encryption failed: %s", type(e).__name__)
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

    # A legacy plaintext row is still READABLE — it may be the only credential able to
    # revoke a live provider Item. Refusing to read it would strand that access, which is
    # strictly worse than reading it once in order to revoke and re-encrypt.
    if ciphertext.startswith(LEGACY_PLAINTEXT_PREFIX):
        logger.error(
            "Legacy PLAINTEXT provider token encountered (id-less alert). Re-encrypt or "
            "revoke it; writing plaintext is no longer possible."
        )
        return ciphertext[len(LEGACY_PLAINTEXT_PREFIX):]

    fernet = get_fernet()          # raises EncryptionNotConfigured when unusable
    try:
        return fernet.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.error("Token decryption failed: %s", type(e).__name__)
        raise ValueError("Token decryption failed. Key may have changed.")


def is_legacy_plaintext(ciphertext: str) -> bool:
    """True when a stored value is a legacy plaintext token (audit helper)."""
    return bool(ciphertext) and ciphertext.startswith(LEGACY_PLAINTEXT_PREFIX)


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
