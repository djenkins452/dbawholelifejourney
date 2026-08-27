# ==============================================================================
# File: apps/finance/services/sync_reconciliation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Recovery net for transaction ingestion when a webhook never arrives.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Scheduled reconciliation — the safety net BEHIND webhooks, never a replacement.

Webhooks stay the primary, low-latency trigger. This exists because they are not
guaranteed: Plaid retries a failed delivery for a bounded window and then stops, and on
2026-08-26 WLJ rejected every delivery for an hour through a defect of its own. Without
a second trigger, a connection whose webhook is lost past the retry window stops
ingesting **permanently** and nothing ever notices.

Design constraints, all deliberate:

* **`/transactions/sync` with the durable cursor ONLY.** Never `/transactions/refresh`
  — that endpoint is separately billed and is not needed to recover a missed webhook.
* **Only genuinely stale connections.** A connection whose webhooks are working is
  never touched, so the steady-state cost of the safety net is zero provider calls.
* **One governed path.** Reconciliation calls the SAME `TransactionSyncService` the
  webhook and manual paths use, so pagination, cursor persistence, provenance,
  classification and the per-connection lock are identical by construction.
"""
from __future__ import annotations

import logging

from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

#: How stale a connection must be before the safety net acts.
#:
#: Chosen, not defaulted: Plaid's webhook retries play out over hours, so reconciling
#: sooner would mostly race deliveries that are still coming. Six hours sits past that
#: window while capping the worst case — a permanently lost webhook costs at most six
#: hours of staleness, four provider calls a day, and nothing at all while webhooks work.
STALE_AFTER_HOURS = 6

#: Per run, so one bad afternoon cannot turn into an unbounded provider stampede.
#: Anything not reached this run is simply picked up by the next one.
MAX_CONNECTIONS_PER_RUN = 25


def stale_cutoff(now=None):
    """The timestamp a connection must have synced after to count as fresh."""
    return (now or timezone.now()) - timezone.timedelta(hours=STALE_AFTER_HOURS)


def _stale_q(cutoff):
    """`last_sync_at` is older than the cutoff, or the connection never synced."""
    return Q(last_sync_at__lt=cutoff) | Q(last_sync_at__isnull=True)


def eligible_connections(now=None, limit=MAX_CONNECTIONS_PER_RUN):
    """Connections a scheduled sync may legitimately touch.

    Every exclusion below is a case where syncing would be wrong, not merely wasteful:

    * not `active` — covers disconnected, error, reauth-required, pending AND
      `revocation_pending`; that last one still holds a token on purpose (it is the only
      credential that can revoke the Item) and must never be used to pull data;
    * soft-deleted (`status`) — the row is gone as far as the product is concerned;
    * no stored token — nothing to authenticate with;
    * inactive user — a disabled account must not have data fetched on its behalf;
    * synced within the freshness window — webhooks are evidently working.
    """
    from apps.finance.models import BankConnection

    cutoff = stale_cutoff(now)
    queryset = (
        BankConnection.objects                      # SoftDeleteManager: excludes deleted
        .filter(connection_status=BankConnection.STATUS_ACTIVE)
        .filter(user__is_active=True)
        .exclude(access_token_encrypted="")
        .filter(_stale_q(cutoff))
        .select_related("user")
        # nulls_first is EXPLICIT on purpose: a bare .order_by("last_sync_at") puts
        # NULLs first on SQLite and LAST on PostgreSQL, so a never-synced connection
        # would have been reconciled last in production and first in tests.
        .order_by(F("last_sync_at").asc(nulls_first=True))
    )
    return list(queryset[:limit])


def describe_selection(now=None, limit=MAX_CONNECTIONS_PER_RUN):
    """Operator-facing dry run. Reports WHY, never WHAT — no financial detail.

    Deliberately carries no institution name, provider identifier, balance, transaction
    or user email: staleness is an operational fact and needs none of them.
    """
    from apps.finance.models import BankConnection

    now = now or timezone.now()
    selected = eligible_connections(now=now, limit=limit)
    total_active = BankConnection.objects.filter(
        connection_status=BankConnection.STATUS_ACTIVE).count()

    rows = []
    for connection in selected:
        age_hours = None
        if connection.last_sync_at:
            age_hours = round(
                (now - connection.last_sync_at).total_seconds() / 3600.0, 1)
        rows.append({
            "connection_pk": connection.pk,
            "hours_since_last_sync": age_hours,      # None = never synced
            "never_synced": connection.last_sync_at is None,
            "historical_complete": connection.historical_update_complete,
        })

    return {
        "now": now.isoformat(),
        "stale_after_hours": STALE_AFTER_HOURS,
        "cutoff": stale_cutoff(now).isoformat(),
        "active_connections": total_active,
        "eligible_count": len(rows),
        "eligible": rows,
    }


def reconcile_connection(connection):
    """Run ONE ordinary incremental sync through the shared governed service.

    Provider failures are normalised to a result dict rather than raised: one
    unreachable institution must not abort the rest of the run.
    """
    from apps.finance.services.sync_service import TransactionSyncService

    try:
        result = TransactionSyncService(connection).sync(trigger="scheduled")
    except Exception as exc:
        logger.warning(
            "Scheduled reconciliation failed for connection %s: %s",
            connection.pk, type(exc).__name__, exc_info=True)
        return {"connection_pk": connection.pk, "ok": False,
                "error": type(exc).__name__}

    if result.get("skipped"):
        # A webhook or manual sync already holds the lock — that is the safety net
        # correctly standing down, not a failure.
        return {"connection_pk": connection.pk, "ok": True, "skipped": True,
                "reason": result.get("reason")}

    if result.get("error"):
        return {"connection_pk": connection.pk, "ok": False,
                "error": str(result["error"])[:120]}

    return {
        "connection_pk": connection.pk,
        "ok": True,
        "added": result.get("added", 0),
        "modified": result.get("modified", 0),
        "removed": result.get("removed", 0),
    }
