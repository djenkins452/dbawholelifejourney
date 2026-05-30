"""
Weight-sync staleness signal — canonical "is Apple Health weight sync OK?".

Single source of truth consumed by BOTH the dashboard/Beth accountability
(via the PIE insight rule) and SAE health state, so the two surfaces can
never disagree about weight recency OR about whether a *sync* (vs the user)
is the reason for a gap.

This does NOT change the proven weight read layer — it reads the same
`WeightEntry` rows by `recorded_at` and only ADDS provenance/staleness
interpretation on top.

Trust rule it enforces: when recent entries came from Apple Health AND a
mobile device is active, a multi-day gap is a *sync failure*, not the user
failing to weigh. The two cases must be narrated differently.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

# Apple Health pushes weight ~daily from a connected scale, so a gap beyond
# this many days with an active sync device strongly implies the sync broke.
SYNC_STALE_THRESHOLD_DAYS = 3

# How many recent entries to inspect when deciding the "dominant" source.
_RECENT_SAMPLE = 10


def get_weight_sync_status(user) -> dict[str, Any]:
    """Return the canonical weight-sync status for a user.

    Read-only. Never raises on the request path. Shape:
        {
          "has_entries": bool,
          "last_entry_at": datetime | None,
          "last_entry_date": date | None,
          "gap_days": int | None,
          "last_source": "apple_health" | "manual" | None,
          "recent_source": "apple_health" | "manual" | None,
          "sync_device_active": bool,
          "sync_expected": bool,   # recent entries were apple_health + device active
          "sync_stale": bool,      # sync_expected AND gap >= threshold
          "stale_threshold_days": int,
        }
    """
    out: dict[str, Any] = {
        "has_entries": False,
        "last_entry_at": None,
        "last_entry_date": None,
        "gap_days": None,
        "last_source": None,
        "recent_source": None,
        "sync_device_active": False,
        "sync_expected": False,
        "sync_stale": False,
        "stale_threshold_days": SYNC_STALE_THRESHOLD_DAYS,
    }

    try:
        from apps.health.models import WeightEntry
        # SAME read layer as accountability/screen — order by recorded_at.
        recent = list(
            WeightEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values("recorded_at", "source")[:_RECENT_SAMPLE]
        )
    except Exception:
        logger.warning("weight_sync: WeightEntry read failed", exc_info=True)
        return out

    if not recent:
        return out

    now = timezone.now()
    latest = recent[0]
    out["has_entries"] = True
    out["last_entry_at"] = latest["recorded_at"]
    out["last_entry_date"] = latest["recorded_at"].date()
    out["last_source"] = latest.get("source")
    out["gap_days"] = max(0, (now - latest["recorded_at"]).days)

    # Dominant source across the recent sample.
    apple = sum(1 for r in recent if r.get("source") == "apple_health")
    out["recent_source"] = (
        "apple_health" if apple >= (len(recent) / 2.0) else "manual"
    )

    out["sync_device_active"] = _has_active_sync_device(user)

    # Sync is "expected" only when the user has been syncing from Apple
    # Health AND a device is active — otherwise a gap is genuinely the user
    # not weighing (manual), which the existing message handles correctly.
    out["sync_expected"] = (
        out["recent_source"] == "apple_health" and out["sync_device_active"]
    )
    out["sync_stale"] = (
        out["sync_expected"]
        and out["gap_days"] is not None
        and out["gap_days"] >= SYNC_STALE_THRESHOLD_DAYS
    )

    return out


def resolve_stale_weight_insight_if_cleared(user) -> int:
    """Resolve any stale weight-gap insight whose underlying condition has
    since cleared in SAE — fires on every dashboard load.

    This is the production fix for the 2026-05-30 trust bug: the post_save
    signal on WeightEntry only catches FUTURE ingests. Pre-existing stale
    Insight rows (created BEFORE that signal deployed) never get a save
    event to trigger them. Without this, a fresh weight already in the DB
    will not clear the stale dashboard warning until the user happens to
    log another weight.

    Cheap and idempotent: reads cached SAE state (no recompute), and only
    issues the dismissal UPDATE when the gap actually cleared. Safe to
    call on every dashboard render.

    Returns the number of insights dismissed (0 if not stale or none active).
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        health = get_module_state(user, "health") or {}
    except Exception:
        logger.debug("weight_sync: SAE read failed (skip cleanup)", exc_info=True)
        return 0

    # Only dismiss when SAE explicitly says the condition has cleared.
    # Conservative defaults so a missing key NEVER triggers dismissal.
    if health.get("weight_sync_stale", True):
        return 0
    gap = health.get("weight_sync_gap_days")
    if gap is None or gap >= 3:
        return 0

    return resolve_weight_gap_insights(user)


def resolve_weight_gap_insights(user) -> int:
    """Dismiss any active 'missing_weight_logging' insight for this user.

    Called from the WeightEntry post_save signal: once a fresh weight arrives
    the condition behind the insight no longer holds, so the dashboard
    accountability layer (which reads persisted PIE Insight rows) must not
    keep showing a stale warning. Without this, dashboard and Beth diverge
    after ingest (Beth re-reads SAE = fresh; dashboard re-reads insight rows
    = stale until 7-day window expires).

    Returns the number of insights dismissed (0 if none were active).
    """
    try:
        from apps.core.ai_insights.models import Insight
        count = Insight.objects.filter(
            user=user,
            insight_type="missing_weight_logging",
            status__in=("new", "read"),
        ).update(status="dismissed")
        if count:
            logger.info(
                "weight_sync: resolved %d stale weight-gap insight(s) user=%s",
                count, getattr(user, "id", "?"),
            )
        return count
    except Exception:
        logger.warning(
            "weight_sync: insight resolution failed user=%s",
            getattr(user, "id", "?"), exc_info=True,
        )
        return 0


def _has_active_sync_device(user) -> bool:
    """True if the user has an active mobile device or a live (non-expired)
    auth token — i.e. Apple Health sync SHOULD be delivering data.

    Defensive: the mobile app is optional; any failure → False (we then
    fall back to the generic "no weight logged" message, never a false
    "sync stopped" claim)."""
    now = timezone.now()
    try:
        from apps.mobile.models import MobileDevice
        if MobileDevice.objects.filter(user=user, is_active=True).exists():
            return True
    except Exception:
        pass
    try:
        from apps.mobile.models import MobileAuthToken
        if MobileAuthToken.objects.filter(
            user=user, is_active=True, expires_at__gt=now,
        ).exists():
            return True
    except Exception:
        pass
    return False
