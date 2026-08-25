# ==============================================================================
# File: apps/finance/services/provider_disconnect.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE one path that withdraws provider (Plaid) access.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Revoke first, forget second — never the other way round.

The failure this exists to prevent: WLJ told the user "disconnected", swallowed the
provider error, and then deleted the access token — leaving the provider's access to
their bank **live forever**, with the only credential that could withdraw it destroyed.

The contract:
  1. ask the provider to remove the Item FIRST;
  2. clear the local token ONLY after the provider confirms;
  3. on failure, KEEP the encrypted token, mark `revocation_pending`, and surface it —
     never report success;
  4. retries are idempotent: an Item the provider no longer has is treated as revoked;
  5. every transition is audited with redacted detail.

Deletion guards live on the model (`BankConnection.delete` / `.soft_delete`) and REFUSE
rather than call out to the network, because an external request inside a delete path —
or inside a user-deletion cascade — is precisely the fragile coupling that strands state.
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from apps.finance.models import BankConnection, BankIntegrationLog

logger = logging.getLogger(__name__)

#: Provider errors meaning "this Item is already gone" — revocation is complete.
ALREADY_GONE_CODES = {"ITEM_NOT_FOUND", "INVALID_ACCESS_TOKEN", "ITEM_NOT_SUPPORTED"}


class RevocationFailed(RuntimeError):
    """The provider did not confirm revocation. Local access token was preserved."""


def _audit(connection, *, success, detail, ip_address=None):
    """Redacted audit trail — reason codes and ids only, never a token or a payload."""
    BankIntegrationLog.objects.create(
        user_id=connection.user_id,
        bank_connection=connection,
        action=BankIntegrationLog.ACTION_DISCONNECT,
        success=success,
        # Reason CODES only — never a token, a provider payload, or an error body.
        details={"reason": (detail or "")[:120]} if detail else {},
        ip_address=ip_address,
    )


def _provider_error_code(exc):
    """Best-effort provider error code, without logging the body."""
    for attr in ("code", "error_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, str) and value:
            return value
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        for code in ALREADY_GONE_CODES:
            if code in body:
                return code
    return ""


def revoke_and_disconnect(connection, *, ip_address=None, plaid_service=None):
    """Withdraw provider access, then forget the credential. Idempotent.

    Returns the refreshed `BankConnection`.
    Raises `RevocationFailed` when the provider did not confirm — with the encrypted
    token still stored so a retry can succeed.
    """
    from apps.finance.services.plaid_service import get_plaid_service

    if connection.connection_status == BankConnection.STATUS_DISCONNECTED and \
            not connection.access_token_encrypted:
        return connection                      # already fully revoked — idempotent no-op

    access_token = connection.get_access_token()
    if not access_token:
        # Nothing to revoke: there is no credential and therefore no live access.
        with db_transaction.atomic():
            connection.mark_disconnected()
            _audit(connection, success=True, detail="", ip_address=ip_address)
        return connection

    service = plaid_service or get_plaid_service()
    try:
        service.remove_item(access_token)
    except Exception as exc:
        code = _provider_error_code(exc)
        if code in ALREADY_GONE_CODES:
            # The provider has no such Item — access IS revoked. Safe to forget.
            with db_transaction.atomic():
                connection.mark_disconnected()
                _audit(connection, success=True, detail="", ip_address=ip_address)
            logger.info("Provider Item already absent; treated as revoked (conn=%s)",
                        connection.pk)
            return connection

        # KEEP the token. It is the only thing that can still revoke this access.
        with db_transaction.atomic():
            connection.mark_revocation_pending(
                f"Provider revocation failed ({type(exc).__name__}"
                + (f"/{code}" if code else "") + "). Access token retained for retry."
            )
            _audit(connection, success=False,
                   detail=f"revocation_failed:{code or type(exc).__name__}",
                   ip_address=ip_address)
        logger.error("Plaid revocation FAILED for connection %s (%s) — token retained",
                     connection.pk, type(exc).__name__)
        raise RevocationFailed(
            "We could not confirm your bank disconnected this connection. Nothing was "
            "discarded — you can retry, and access remains withdrawable."
        )

    with db_transaction.atomic():
        connection.mark_disconnected()
        _audit(connection, success=True, detail="", ip_address=ip_address)
    return connection


def retry_pending_revocations(user=None):
    """Retry every connection stuck in `revocation_pending`. Safe to run repeatedly."""
    queryset = BankConnection.objects.filter(
        connection_status=BankConnection.STATUS_REVOCATION_PENDING)
    if user is not None:
        queryset = queryset.filter(user=user)

    results = {"attempted": 0, "revoked": 0, "still_pending": 0}
    for connection in queryset.iterator():
        results["attempted"] += 1
        try:
            revoke_and_disconnect(connection)
            results["revoked"] += 1
        except RevocationFailed:
            results["still_pending"] += 1
        except Exception:
            results["still_pending"] += 1
            logger.error("Unexpected error retrying revocation for connection %s",
                         connection.pk, exc_info=True)
    return results


def assert_no_live_provider_access(user):
    """Guard for account closure: refuse while any provider access is still live."""
    live = [c.pk for c in BankConnection.objects.filter(user=user)
            if c.has_live_provider_access]
    if live:
        raise ValidationError(
            f"{len(live)} bank connection(s) still have live provider access. "
            "Disconnect them first so the provider revokes access."
        )
    return True
