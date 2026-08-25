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
