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


def resolve_stale_weight_insight_if_cleared(user) -> dict:
    """Resolve EVERY stale weight-gap dashboard artifact whose underlying
    condition has cleared — fires on every dashboard load. Deterministic.

    Covers BOTH stores the v3 accountability card reads from:
      - core_ai_insight rows (insight_type='missing_weight_logging')
        → status flipped to 'dismissed'
      - ai_guidance.GuidanceItem rows scoped to module='health' with a
        weight-sync title → is_active flipped to False

    SELF-SUFFICIENT: reads `WeightEntry.recorded_at` DIRECTLY, not SAE.
    Immune to SAE state shape (missing/stale `weight_sync_*` keys).

    Returns a diagnostic dict consumed by [DASHBOARD_WEIGHT_DEBUG] logging:
        {
          latest_recorded_at, gap_days,
          insight_active_before, insight_dismissed_count, insight_dismissed_ids,
          guidance_active_before, guidance_deactivated_count,
          guidance_deactivated_ids, guidance_titles,
        }
    """
    from django.db.models import Q
    from apps.core.ai_insights.models import Insight
    from apps.core.ai_guidance.models import GuidanceItem
    from apps.health.models import WeightEntry

    result = {
        "latest_recorded_at": None,
        "gap_days": None,
        "insight_active_before": 0,
        "insight_dismissed_count": 0,
        "insight_dismissed_ids": [],
        "guidance_active_before": 0,
        "guidance_deactivated_count": 0,
        "guidance_deactivated_ids": [],
        "guidance_titles": [],
        "preserved_reason": None,
    }

    # ── Both stale-row queries ──
    # Insight: exact by insight_type (rule-authored, rename-safe).
    insight_qs = Insight.objects.filter(
        user=user,
        insight_type="missing_weight_logging",
        status__in=("new", "read"),
    )
    # GuidanceItem: no taxonomy for weight-sync guidance exists yet, so we
    # use a documented title-keyword bridge scoped to module='health' (same
    # metadata-first/name-fallback pattern already used by
    # auto_complete_routine_schedules). Retire when guidance_type covers
    # this domain.
    guidance_qs = GuidanceItem.objects.filter(
        user=user,
        module="health",
        is_active=True,
    ).filter(
        Q(title__icontains="weight sync")
        | Q(title__icontains="weight entry")
        | Q(title__icontains="Apple Health weight")
    )

    result["insight_active_before"] = insight_qs.count()
    result["guidance_active_before"] = guidance_qs.count()

    if not (result["insight_active_before"] or result["guidance_active_before"]):
        result["preserved_reason"] = "no_active_rows"
        return result

    # ── Canonical truth: latest WeightEntry directly ──
    latest = (
        WeightEntry.objects.filter(user=user)
        .order_by("-recorded_at")
        .only("recorded_at")
        .first()
    )
    if not latest:
        result["preserved_reason"] = "no_weight_entries"
        return result

    result["latest_recorded_at"] = latest.recorded_at.isoformat()
    gap = max(0, (timezone.now() - latest.recorded_at).days)
    result["gap_days"] = gap

    if gap >= 3:
        # Gap is real → both warnings are correct → preserve.
        result["preserved_reason"] = f"gap_real_{gap}d"
        return result

    # ── Dismiss / deactivate (capture IDs first for deterministic logs) ──
    if result["insight_active_before"]:
        result["insight_dismissed_ids"] = list(
            insight_qs.values_list("id", flat=True)
        )
        result["insight_dismissed_count"] = insight_qs.update(status="dismissed")

    if result["guidance_active_before"]:
        guidance_rows = list(guidance_qs.values("id", "title"))
        result["guidance_deactivated_ids"] = [g["id"] for g in guidance_rows]
        result["guidance_titles"] = [g["title"] for g in guidance_rows]
        result["guidance_deactivated_count"] = guidance_qs.update(is_active=False)

    return result


def resolve_weight_gap_insights(user) -> dict:
    """Unconditionally dismiss EVERY active weight-gap artifact for a user.

    Called from the WeightEntry post_save signal — a fresh weight arrived,
    so by definition the condition has cleared. Covers BOTH stores the
    dashboard accountability card reads from (Insight rows + GuidanceItem
    rows) so a stale warning cannot persist in either layer.

    Returns a diagnostic dict (same shape used by the gated wrapper):
        {insight_dismissed_count, insight_dismissed_ids,
         guidance_deactivated_count, guidance_deactivated_ids}
    """
    from django.db.models import Q
    out = {
        "insight_dismissed_count": 0,
        "insight_dismissed_ids": [],
        "guidance_deactivated_count": 0,
        "guidance_deactivated_ids": [],
    }
    try:
        from apps.core.ai_insights.models import Insight
        qs = Insight.objects.filter(
            user=user,
            insight_type="missing_weight_logging",
            status__in=("new", "read"),
        )
        out["insight_dismissed_ids"] = list(qs.values_list("id", flat=True))
        out["insight_dismissed_count"] = qs.update(status="dismissed")
    except Exception:
        logger.warning(
            "weight_sync: insight dismissal failed user=%s",
            getattr(user, "id", "?"), exc_info=True,
        )
    try:
        from apps.core.ai_guidance.models import GuidanceItem
        gqs = GuidanceItem.objects.filter(
            user=user, module="health", is_active=True,
        ).filter(
            Q(title__icontains="weight sync")
            | Q(title__icontains="weight entry")
            | Q(title__icontains="Apple Health weight")
        )
        out["guidance_deactivated_ids"] = list(gqs.values_list("id", flat=True))
        out["guidance_deactivated_count"] = gqs.update(is_active=False)
    except Exception:
        logger.warning(
            "weight_sync: guidance deactivation failed user=%s",
            getattr(user, "id", "?"), exc_info=True,
        )
    if out["insight_dismissed_count"] or out["guidance_deactivated_count"]:
        logger.info(
            "weight_sync: cleared user=%s insights=%s guidance=%s",
            getattr(user, "id", "?"),
            out["insight_dismissed_count"],
            out["guidance_deactivated_count"],
        )
    return out


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
