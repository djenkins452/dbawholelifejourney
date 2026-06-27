"""
Medication Intelligence operational telemetry (Sprint 9B).

Follows the existing Ops Wall convention (``wlj:ops:*`` cache keys, background
compute → cache → read-only request path). ``compute_*`` aggregates metrics and
writes the snapshot; ``get_*`` reads the snapshot only (returns None when not yet
populated — never live-computes on the request path, per the CLAUDE.md rule).
"""

import logging

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

OPS_KEY = "wlj:ops:med_intelligence"
OPS_TTL = 60 * 60 * 25  # 25h, matching other ops snapshots
PHYSICIAN_COUNTER_KEY = "wlj:ops:med_physician_summaries"


def record_physician_summary_generated():
    """Best-effort counter for physician summaries generated (telemetry only)."""
    try:
        try:
            cache.incr(PHYSICIAN_COUNTER_KEY)
        except ValueError:
            cache.set(PHYSICIAN_COUNTER_KEY, 1, OPS_TTL)
    except Exception:  # pragma: no cover - telemetry must never break a request
        logger.debug("physician summary counter failed", exc_info=True)


def compute_medication_intelligence_ops():
    """Aggregate Medication Intelligence ops metrics and write the snapshot.

    Intended to run in the background (SAME cycle / ISE). Light: bounded GROUP BY
    aggregates over MedicationScanDraft + a counter read."""
    from django.db.models import Count
    from apps.health.models import MedicationScanDraft

    by_status = dict(
        MedicationScanDraft.objects.values_list("review_status")
        .annotate(n=Count("id")).values_list("review_status", "n")
    )
    confirmed = by_status.get("confirmed", 0)
    rejected = by_status.get("rejected", 0)
    pending = by_status.get("pending_review", 0)
    resolved = confirmed + rejected

    # Confirmation actions (duplicate resolutions = update/replace).
    by_action = dict(
        MedicationScanDraft.objects.filter(review_status="confirmed")
        .values_list("confirmation_action")
        .annotate(n=Count("id")).values_list("confirmation_action", "n")
    )
    duplicate_resolutions = by_action.get("update", 0) + by_action.get("replace", 0)

    # Confidence distribution (buckets) across all drafts.
    buckets = {"high(>=0.85)": 0, "medium(0.55-0.85)": 0, "low(<0.55)": 0, "none": 0}
    for c in MedicationScanDraft.objects.values_list("overall_confidence", flat=True):
        if c is None:
            buckets["none"] += 1
        elif c >= 0.85:
            buckets["high(>=0.85)"] += 1
        elif c >= 0.55:
            buckets["medium(0.55-0.85)"] += 1
        else:
            buckets["low(<0.55)"] += 1

    snapshot = {
        "computed_at": timezone.now().isoformat(),
        "acquisition": {
            "total_drafts": sum(by_status.values()),
            "pending_review": pending,
            "confirmed": confirmed,
            "rejected": rejected,
            "expired": by_status.get("expired", 0),
            "confirmation_rate": round(confirmed / resolved, 3) if resolved else None,
            "duplicate_resolutions": duplicate_resolutions,
        },
        "confidence_distribution": buckets,
        "by_source": dict(
            MedicationScanDraft.objects.values_list("source")
            .annotate(n=Count("id")).values_list("source", "n")
        ),
        "physician_summaries_generated": cache.get(PHYSICIAN_COUNTER_KEY, 0),
    }
    cache.set(OPS_KEY, snapshot, OPS_TTL)
    return snapshot


def get_medication_intelligence_ops():
    """Read the ops snapshot (Ops Wall). Returns None when not yet populated —
    a 'pending' state; NEVER live-computes on the request path."""
    return cache.get(OPS_KEY)
