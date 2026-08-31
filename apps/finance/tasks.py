# ==============================================================================
# File: apps/finance/tasks.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: F1 — background detection of Finance attribution opportunities.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Finance background work.

Runs in the worker, never on a request path (`docs/WLJ_REQUEST_PATH_SAFETY.md`), on a
CRONTAB schedule — Railway's ephemeral filesystem resets `PersistentScheduler` on every
restart, which starves long *interval* tasks.

Idempotent by construction: detection is a pure function of current truth written through
`Insight.dedupe_key`, so a re-run updates rather than duplicates. **No model call happens
here, ever** — this is deterministic comparison, not classification.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="apps.finance.tasks.detect_finance_opportunities")
def detect_finance_opportunities(user_id=None):
    """Recompute entity-payment-mismatch findings for one user, or every active user."""
    from django.contrib.auth import get_user_model

    from apps.finance.models import FinanceOpportunity, TransactionAttribution
    from apps.finance.services import opportunity_lifecycle as lifecycle
    from apps.finance.services.opportunity_detection import build_findings, record_findings

    User = get_user_model()
    if user_id is not None:
        users = User.objects.filter(id=user_id)
    else:
        # Only users who actually have attribution truth — no work for anyone else.
        user_ids = (TransactionAttribution.objects
                    .filter(attribution_status=TransactionAttribution.STATUS_ACTIVE)
                    .values_list("user_id", flat=True).distinct())
        users = User.objects.filter(id__in=list(user_ids))

    totals = {"users": 0, "created": 0, "updated": 0, "resolved": 0,
              "retired": 0, "verified": 0}
    for user in users.iterator():
        try:
            findings = build_findings(user)
            result = record_findings(user, findings)
            # F3: keep the lifecycle in step with detection, then look for evidence that
            # an accepted change actually happened. WLJ observes; it never acts outside.
            live_keys = lifecycle.sync_from_findings(user, findings)
            totals["retired"] += lifecycle.retire_resolved(user, live_keys)
            watching = FinanceOpportunity.objects.filter(
                user=user, state__in=FinanceOpportunity.WATCHING_STATES,
            ).select_related("attributed_entity", "paid_by_entity")
            for opportunity in watching:
                if lifecycle.verify_from_truth(user, opportunity) is not None:
                    totals["verified"] += 1
        except Exception:
            # One user's bad data must never stop the sweep — but it must be VISIBLE.
            logger.error("Finance opportunity detection failed for user %s",
                         user.id, exc_info=True)
            continue
        totals["users"] += 1
        for key in ("created", "updated", "resolved"):
            totals[key] += result[key]
    logger.info("Finance opportunity detection: %s", totals)
    return totals


@shared_task(name="apps.finance.tasks.reconcile_stale_bank_connections")
def reconcile_stale_bank_connections():
    """Recover transaction ingestion for connections whose webhook never arrived.

    Webhooks remain the primary trigger; this is the net beneath them. Plaid retries a
    failed delivery for a bounded window and then gives up, so without a second trigger
    a connection that misses its webhook stops ingesting permanently and nothing
    notices. On 2026-08-26 WLJ rejected every delivery for an hour through its own
    defect — exactly the failure this recovers from.

    Only genuinely stale, active, token-bearing connections belonging to enabled users
    are touched, so while webhooks work this costs zero provider calls. Uses
    `/transactions/sync` with the durable cursor through the shared sync service —
    NEVER the separately billed `/transactions/refresh`.
    """
    from apps.finance.services.sync_reconciliation import (
        MAX_CONNECTIONS_PER_RUN, STALE_AFTER_HOURS,
        eligible_connections, reconcile_connection,
    )

    connections = eligible_connections()
    if not connections:
        logger.info("Finance reconciliation: no connections older than %sh.",
                    STALE_AFTER_HOURS)
        return {"eligible": 0, "synced": 0, "skipped": 0, "failed": 0}

    summary = {"eligible": len(connections), "synced": 0, "skipped": 0,
               "failed": 0, "added": 0}
    for connection in connections:
        outcome = reconcile_connection(connection)
        if not outcome["ok"]:
            summary["failed"] += 1
        elif outcome.get("skipped"):
            summary["skipped"] += 1
        else:
            summary["synced"] += 1
            summary["added"] += outcome.get("added", 0)

    # Counts only — never an institution, provider id, balance or transaction.
    logger.info(
        "Finance reconciliation: eligible=%s synced=%s skipped=%s failed=%s added=%s "
        "(threshold %sh, cap %s)",
        summary["eligible"], summary["synced"], summary["skipped"],
        summary["failed"], summary["added"], STALE_AFTER_HOURS,
        MAX_CONNECTIONS_PER_RUN)

    if summary["failed"]:
        logger.warning(
            "Finance reconciliation could not sync %s connection(s); ingestion for "
            "those remains stale and will be retried next run.", summary["failed"])

    return summary


@shared_task(name="apps.finance.tasks.detect_recurring_and_opportunities")
def detect_recurring_and_opportunities(user_id=None):
    """Look for recurring patterns and the savings they imply. Worker-only.

    This classifies the whole transaction population and then walks it looking for
    schedules, which is far too much work for a request path — a Gunicorn worker doing
    this is a worker not serving anyone. It is enqueued from the page and runs here.

    Everything it produces is a CANDIDATE. It confirms nothing, and it never reopens a
    decision a person has already made.
    """
    from django.contrib.auth import get_user_model

    from apps.finance.services.finance_calc import opportunities as OPP
    from apps.finance.services.finance_calc import recurring as REC

    User = get_user_model()
    users = ([User.objects.filter(pk=user_id).first()] if user_id
             else list(User.objects.filter(is_active=True)))

    results = []
    for user in filter(None, users):
        try:
            detected = REC.persist(user, REC.detect(user), commit=True)
            # Opportunities depend on CONFIRMED series, so a first run usually finds
            # none. That is correct: it is waiting for the person, not broken.
            proposed = OPP.persist(user, OPP.generate(user), commit=True)
            results.append({"user": user.pk, "recurring": detected,
                            "opportunities": proposed})
        except Exception:
            logger.error("Recurring/opportunity detection failed for user %s",
                         user.pk, exc_info=True)
    return {"users": len(results), "results": results}
