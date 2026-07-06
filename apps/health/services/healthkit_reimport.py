"""HealthKit historical reimport — user-triggered repair of noon-defaulted samples.

The server can't read HealthKit (on-device), so this coordinates a safe hand-off:
  1. User clicks "Re-import from Apple Health" (web) -> request_reimport() creates a
     pending HealthReimportRequest (superseding any earlier open one).
  2. The native app polls /health/sync-status/, sees pending_directive(), re-queries
     HealthKit over the window, and re-POSTs each sample to /health/ingest/ — which
     self-heals noon rows by the stable sample UUID (never fabricating a time).
  3. The app calls /health/reimport/complete/ -> complete_request() records the counts.

Idempotent and safe to run repeatedly. No timestamps are fabricated; Apple Health is the
source of truth and the ingest self-heal does the actual repair in place.
"""
from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def request_reimport(user, metrics=None, since_date=None):
    """Create a fresh pending reimport request, superseding any earlier OPEN one for the
    user (so we never queue duplicates). Returns the new HealthReimportRequest."""
    from apps.mobile.models import HealthReimportRequest
    metrics = list(metrics) if metrics else list(HealthReimportRequest.DEFAULT_METRICS)
    # Supersede any still-open request — the newest ask wins.
    (HealthReimportRequest.objects
     .filter(user=user, status__in=(HealthReimportRequest.STATUS_PENDING,
                                    HealthReimportRequest.STATUS_IN_PROGRESS))
     .update(status=HealthReimportRequest.STATUS_FAILED, note="superseded by a newer request",
             completed_at=timezone.now()))
    return HealthReimportRequest.objects.create(
        user=user, metrics=metrics, since_date=since_date,
        status=HealthReimportRequest.STATUS_PENDING)


def pending_directive(user):
    """The open reimport directive for the app to fulfil, or None. Serving it marks the
    request in_progress (so the UI can show 'reimport running') — idempotent."""
    from apps.mobile.models import HealthReimportRequest
    req = (HealthReimportRequest.objects
           .filter(user=user, status__in=(HealthReimportRequest.STATUS_PENDING,
                                           HealthReimportRequest.STATUS_IN_PROGRESS))
           .order_by("-created_at").first())
    if req is None:
        return None
    if req.status == HealthReimportRequest.STATUS_PENDING:
        req.status = HealthReimportRequest.STATUS_IN_PROGRESS
        req.acknowledged_at = timezone.now()
        req.save(update_fields=["status", "acknowledged_at", "updated_at"])
    return {
        "request_id": req.id,
        "metrics": list(req.metrics or []),
        "since": req.since_date.isoformat() if req.since_date else None,
        "status": req.status,
    }


def complete_request(user, request_id, *, scanned=0, created=0, updated=0, skipped=0,
                     failed=0, note=""):
    """Record the app's fulfilment counts and close the request. Returns the request or
    None if it doesn't belong to the user."""
    from apps.mobile.models import HealthReimportRequest
    req = HealthReimportRequest.objects.filter(user=user, id=request_id).first()
    if req is None:
        return None
    req.scanned = int(scanned or 0)
    req.created = int(created or 0)
    req.updated = int(updated or 0)
    req.skipped = int(skipped or 0)
    req.failed = int(failed or 0)
    req.status = HealthReimportRequest.STATUS_COMPLETED
    req.completed_at = timezone.now()
    if note:
        req.note = note[:255]
    req.save(update_fields=["scanned", "created", "updated", "skipped", "failed",
                            "status", "completed_at", "note", "updated_at"])
    logger.info("healthkit_reimport: completed user=%s req=%s scanned=%s updated=%s",
                getattr(user, "id", "?"), request_id, req.scanned, req.updated)
    return req


def latest_request(user):
    """The user's most recent reimport request (any status), for the Settings UI."""
    from apps.mobile.models import HealthReimportRequest
    return HealthReimportRequest.objects.filter(user=user).order_by("-created_at").first()
