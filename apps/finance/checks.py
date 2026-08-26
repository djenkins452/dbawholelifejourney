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
FINANCE_REDIRECT_NOT_HTTPS = "finance.E003"
FINANCE_REDIRECT_FOREIGN_HOST = "finance.E004"
FINANCE_REDIRECT_UNROUTED = "finance.E005"


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


@register()
def plaid_redirect_uri_check(app_configs, **kwargs):
    """A configured redirect URI must be HTTPS, ours, and actually routed.

    Plaid rejects `link/token/create` outright when `redirect_uri` is not registered with
    them — so a wrong value here breaks EVERY connection, not just OAuth ones. And a URI
    that is registered but not routed sends the user from their bank to a 404 with their
    connection half-finished. Both failures are cheap to catch at deploy time and
    expensive to discover in production, which is exactly what happened on 2026-08-26.
    """
    from urllib.parse import urlparse

    redirect_uri = (getattr(settings, "PLAID_REDIRECT_URI", "") or "").strip()
    if not redirect_uri:
        return []                      # unset is valid: OAuth institutions are not offered

    errors = []
    parsed = urlparse(redirect_uri)

    if parsed.scheme != "https":
        errors.append(Error(
            f"PLAID_REDIRECT_URI must use https (got {parsed.scheme or 'no scheme'!r}).",
            hint="Banks will not redirect to a non-HTTPS URI.",
            id=FINANCE_REDIRECT_NOT_HTTPS,
        ))

    allowed = {h.lstrip(".") for h in getattr(settings, "ALLOWED_HOSTS", []) if h != "*"}
    host = (parsed.hostname or "").lower()
    if allowed and host and not any(
            host == a.lower() or host.endswith("." + a.lower()) for a in allowed):
        errors.append(Error(
            f"PLAID_REDIRECT_URI host {host!r} is not one of this site's ALLOWED_HOSTS.",
            hint="The redirect must return the user to WLJ itself, never to another "
                 "origin.",
            id=FINANCE_REDIRECT_FOREIGN_HOST,
        ))

    path = parsed.path or "/"
    try:
        from django.urls import Resolver404, resolve
        try:
            resolve(path)
        except Resolver404:
            errors.append(Error(
                f"PLAID_REDIRECT_URI path {path!r} is not routed in WLJ — a bank would "
                "return the user to a 404.",
                hint="Expected the OAuth return route "
                     "(finance:plaid_oauth_return, /finance/plaid/oauth/).",
                id=FINANCE_REDIRECT_UNROUTED,
            ))
    except Exception:                  # pragma: no cover - URLconf not ready
        pass

    return errors
