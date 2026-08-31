# ==============================================================================
# File: apps/finance/tasks_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P11/P12 — scheduled Finance intelligence. Bounded, locked, idempotent.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Background work that must never invent a conclusion because a clock fired.

A scheduled job runs whether or not there is anything to say. That is exactly when a
system starts manufacturing findings: the sweep ran, so it produces output, so a
household is told something. Every job here is allowed — expected — to do nothing and
report that it did nothing.

Four properties, on all of them:

**No provider calls.** None of these touches Plaid. Not `/transactions/refresh`, not
`/liabilities`, nothing billed. They read what WLJ already holds.

**Locked.** A user-level lock keeps a scheduled pass, a webhook-driven pass and a manual
click from running the same computation over the same rows at once.

**Bounded.** Batches are capped and users are selected by whether they have anything to
process, so a sweep cannot grow into an outage as the user base does.

**Idempotent.** Re-running writes nothing new. Every one of these can be run twice by
accident, and eventually will be.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager

from celery import shared_task

logger = logging.getLogger(__name__)

#: How long a user-level lock survives if a worker dies mid-pass. Long enough that a
#: slow run is not clobbered, short enough that a crash does not block the next day.
LOCK_TIMEOUT_SECONDS = 55 * 60

#: Users processed per sweep. A cap that is visible in the result, never a silent
#: truncation — the report says how many were skipped.
BATCH_SIZE = 200


@contextmanager
def user_lock(name, user_id, *, timeout=LOCK_TIMEOUT_SECONDS):
    """Hold a per-user lock, or yield False so the caller can skip cleanly.

    Built on `cache.add`, which is atomic: whoever adds the key first wins, and the
    loser does not wait. A scheduled pass that collides with a manual one should step
    aside, not queue up behind it and run the same work twice.
    """
    from django.core.cache import cache

    key = f"wlj:finance:lock:{name}:{user_id}"
    acquired = False
    try:
        acquired = bool(cache.add(key, "1", timeout))
        yield acquired
    finally:
        if acquired:
            try:
                cache.delete(key)
            except Exception:
                # A lock we cannot release will expire on its own. Losing the release
                # is survivable; letting it raise and lose the WORK is not.
                logger.warning("Could not release finance lock %s", key)


def _finance_users(limit=BATCH_SIZE):
    """Users with Finance enabled and something to work on. Never every account."""
    from django.contrib.auth import get_user_model

    from apps.finance.models import Transaction

    User = get_user_model()
    ids = list(Transaction.objects.values_list("user_id", flat=True).distinct())
    return list(User.objects.filter(id__in=ids, is_active=True)[:limit]), len(ids)


def _sweep(name, work, *, limit=BATCH_SIZE):
    """Run `work(user)` over eligible users, safely. Returns a report, never raises."""
    users, eligible = _finance_users(limit=limit)
    results, skipped_locked, failed = [], 0, 0

    for user in users:
        with user_lock(name, user.pk) as acquired:
            if not acquired:
                skipped_locked += 1
                continue
            try:
                outcome = work(user)
                if outcome:
                    results.append({"user": user.pk, **outcome})
            except Exception:
                # One user's bad data must not cost every other user their sweep.
                failed += 1
                logger.error("Finance sweep %s failed for user %s", name, user.pk,
                             exc_info=True)

    return {
        "job": name,
        "eligible_users": eligible,
        "processed": len(users),
        "skipped_over_batch": max(0, eligible - len(users)),
        "skipped_locked": skipped_locked,
        "failed": failed,
        "results": results,
    }


# ---------------------------------------------------------------------------
# The jobs
# ---------------------------------------------------------------------------

@shared_task(name="apps.finance.tasks_intelligence.sweep_recurring_detection")
def sweep_recurring_detection():
    """Look for new recurring patterns. Proposes candidates; confirms nothing."""
    def work(user):
        from apps.finance.services.finance_calc import recurring as REC
        report = REC.persist(user, REC.detect(user), commit=True)
        return report if report["created"] else None

    return _sweep("recurring_detection", work)


@shared_task(name="apps.finance.tasks_intelligence.sweep_role_reconciliation")
def sweep_role_reconciliation():
    """Classify anything unclassified, and detect classifier drift.

    Drift is the interesting part: when the classifier version moves, previously
    written roles are stale. This reports how many rows disagree with the current
    classifier WITHOUT rewriting them — a silent mass reclassification is not something
    a cron job gets to do.
    """
    def work(user):
        from apps.finance.models import Transaction
        from apps.finance.services.finance_calc import backfill
        from apps.finance.services.finance_calc import roles as R

        unclassified = Transaction.objects.filter(
            user=user, economic_role__isnull=True).count()
        drifted = Transaction.objects.filter(user=user).exclude(
            role_classifier_version=R.CLASSIFIER_VERSION).exclude(
            role_classifier_version="").count()

        written = 0
        if unclassified:
            # Only the genuinely unclassified are written. A row that merely disagrees
            # with a newer classifier is REPORTED, never rewritten on a schedule.
            report = backfill.run(user, commit=True)
            written = report["written"]

        if not (unclassified or drifted):
            return None
        return {"unclassified": unclassified, "written": written,
                "classifier_drift": drifted,
                "current_classifier": R.CLASSIFIER_VERSION}

    return _sweep("role_reconciliation", work)


@shared_task(name="apps.finance.tasks_intelligence.sweep_net_worth_snapshots")
def sweep_net_worth_snapshots():
    """Record today's position. One per user per day, updated in place."""
    def work(user):
        from apps.finance.services.finance_calc import net_worth as NW
        result = NW.take_snapshot(user, commit=True)
        return result if result.get("created") else None

    return _sweep("net_worth_snapshot", work)


@shared_task(name="apps.finance.tasks_intelligence.sweep_opportunities")
def sweep_opportunities():
    """Re-derive savings opportunities. Never reopens a decision."""
    def work(user):
        from apps.finance.services.finance_calc import opportunities as OPP
        report = OPP.persist(user, OPP.generate(user), commit=True)
        return report if report["created"] else None

    return _sweep("opportunity_reevaluation", work)


@shared_task(name="apps.finance.tasks_intelligence.sweep_plan_outcomes")
def sweep_plan_outcomes():
    """Measure whether accepted plans actually produced their saving."""
    def work(user):
        from apps.finance.services.finance_calc import outcomes as OUT
        report = OUT.measure_all(user, commit=True)
        return report if report["measured"] else None

    return _sweep("plan_outcomes", work)


@shared_task(name="apps.finance.tasks_intelligence.sweep_data_health")
def sweep_data_health():
    """Evaluate what is stale, missing or unresolved. Reports; never concludes."""
    def work(user):
        from apps.finance.services.finance_calc import data_health as DH
        report = DH.evaluate(user)
        return report if report["issues"] else None

    return _sweep("data_health", work)
