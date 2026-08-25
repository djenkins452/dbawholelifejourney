# ==============================================================================
# File: apps/finance/checks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deployment validation for provider-credential encryption.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deploy-time validation: a provider integration may not run without encryption.

Django system checks run on `manage.py check` AND before `migrate`, which the Railway
release phase executes on every deploy — so a misconfigured environment fails the deploy
instead of quietly storing a bank credential in the clear.

The key VALUE is never read into a message; only its usability is reported.
"""
from django.conf import settings
from django.core.checks import Error, Warning, register

FINANCE_ENCRYPTION_MISSING = "finance.E001"
FINANCE_ENCRYPTION_INVALID = "finance.E002"
FINANCE_ENCRYPTION_DEV = "finance.W001"


@register()
def bank_token_encryption_check(app_configs, **kwargs):
    """Refuse to deploy a Plaid-configured environment without usable encryption."""
    from apps.finance.services.encryption import (
        EncryptionNotConfigured,
        get_fernet,
    )

    plaid_configured = bool(getattr(settings, "PLAID_CLIENT_ID", "")
                            and getattr(settings, "PLAID_SECRET", ""))
    key_present = bool(getattr(settings, "BANK_TOKEN_ENCRYPTION_KEY", ""))
    debug = getattr(settings, "DEBUG", False)

    if not key_present:
        message = ("BANK_TOKEN_ENCRYPTION_KEY is not set, so provider access tokens "
                   "cannot be encrypted at rest.")
        hint = ("Generate one with `python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\"` and set it on Web AND Worker. "
                "Token storage fails closed without it — a Plaid connection cannot be "
                "created.")
        if plaid_configured and not debug:
            return [Error(message, hint=hint, id=FINANCE_ENCRYPTION_MISSING)]
        return [Warning(message + " Plaid is not configured, so nothing can store a "
                        "token yet.", hint=hint, id=FINANCE_ENCRYPTION_DEV)]

    try:
        get_fernet()
    except EncryptionNotConfigured:
        return [Error(
            "BANK_TOKEN_ENCRYPTION_KEY is set but unusable (not a valid Fernet key).",
            hint="It must be a 32-byte url-safe base64 key from Fernet.generate_key(). "
                 "The value is never logged.",
            id=FINANCE_ENCRYPTION_INVALID,
        )]
    return []
