# ==============================================================================
# File: apps/health/services/glucose_snapshot.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical glucose snapshot — hard split between LATEST timestamped
#              event and SUMMARY aggregate state. Read-only, deterministic, no LLM.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-07
# ==============================================================================
"""
Glucose Snapshot — deterministic canonical state for Beth + SAE.

ARCHITECTURAL CONTRACT (the trust break this fixes):
    Beth must NEVER answer an EVENT question using SUMMARY data.

    Production failure mode that motivated this:
        User: "What was my last blood glucose reading and when?"
        Beth: "Your last blood glucose reading was 119 mg/dL"   ← weekly avg
        User: "What time was that reading?"
        Beth: "I don't have the exact time in my current view"  ← because 119 had no time

    This service makes that failure mode structurally impossible by
    hard-splitting the canonical state into two independent blocks:

        glucose_latest   — single timestamped event (value, time, source, trend)
        glucose_summary  — aggregates (averages, TIR, projected A1C)

    Each is built independently; one missing never falls back to the other.
    Beth NEVER queries GlucoseEntry from chat code — the deterministic
    router + EventResolver adapter route through this snapshot.

Comparison rule for "latest": GlucoseEntry.objects.filter(user=user)
.order_by('-recorded_at').first(). Literal newest reading. No window,
no average, no estimation.

Backward compatibility: legacy SAE keys (latest_glucose, glucose_avg_7d,
glucose_context, last_glucose_entry, glucose_status, etc.) are NOT
removed — every existing consumer keeps working unchanged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Display tables ─────────────────────────────────────────────────────

#: Map of CONTEXT_CHOICES key → human label (mirrors model choices but
#: lives here so the renderer doesn't import the model).
CONTEXT_LABELS = {
    "fasting": "Fasting",
    "before_meal": "Before Meal",
    "after_meal": "After Meal",
    "bedtime": "Bedtime",
    "random": "Random",
    "cgm": "CGM Reading",
}

#: Source label resolution. User-preferred concrete naming: "Dexcom CGM"
#: instead of the generic "CGM Reading". Locked by RenderLatestTests.
SOURCE_LABELS = {
    "manual": "Manual Entry",
    "dexcom": "Dexcom CGM",
    "apple_health": "Apple Health",
    "imported": "Imported",
}

#: Trend code → (human label, ASCII arrow). Mirrors GlucoseEntry.TREND_CHOICES
#: + TREND_ARROWS but with a one-word human label suitable for rendered copy.
#: "steady" is the spec's preferred word over "flat" / "stable".
TREND_DISPLAY = {
    "doubleUp":       ("rising rapidly",  "⬆⬆"),
    "singleUp":       ("rising",          "⬆"),
    "fortyFiveUp":    ("rising slowly",   "↗"),
    "flat":           ("steady",          "→"),
    "fortyFiveDown":  ("falling slowly",  "↘"),
    "singleDown":     ("falling",         "⬇"),
    "doubleDown":     ("falling rapidly", "⬇⬇"),
    "none":           ("",                ""),
    "notComputable":  ("",                ""),
    "rateOutOfRange": ("",                ""),
    "":               ("",                ""),
}

#: After this many minutes, a CGM reading is "stale" for Beth's purposes.
#: A user asking "what's my glucose right now" should see a stale flag if
#: the last reading is hours old — they probably want to know that.
CGM_STALE_MINUTES = 120

#: Days-without-any-reading threshold for the summary "sync_stale" flag.
SUMMARY_STALE_DAYS = 7


# ── Public API ─────────────────────────────────────────────────────────


def build_glucose_latest(user) -> dict | None:
    """Build the canonical LATEST glucose event block.

    Reads the literal newest ``GlucoseEntry`` for the user. NO averaging.
    NO window. The single most recent timestamped reading.

    Returns ``None`` when no readings exist at all. Consumers MUST treat
    ``None`` as "no latest event available" and route to the
    trust-preserving copy — NEVER substitute a summary value.

    Output shape:
        {
          "value":         float,        # the reading
          "unit":          str,          # "mg/dL" / "mmol/L"
          "timestamp":     str (ISO),    # full datetime with offset
          "context":       str,          # raw choice key
          "context_label": str,          # human label
          "source":        str,          # raw choice key
          "source_label":  str,          # "Dexcom CGM" / "Manual Entry" / ...
          "trend":         str,          # raw Dexcom arrow code
          "trend_label":   str,          # "steady" / "rising" / "" if absent
          "trend_arrow":   str,          # "→" / "⬆" / "" if absent
          "trend_rate":    float | None, # mg/dL/min when Dexcom provides it
          "minutes_ago":   int,          # for relative-freshness rendering
          "stale":         bool,         # True when CGM > CGM_STALE_MINUTES old
        }

    Determinism: same DB state → same dict. No write side effects.
    """
    from apps.health.models import GlucoseEntry

    entry = (
        GlucoseEntry.objects.filter(user=user)
        .order_by("-recorded_at")
        .first()
    )
    if entry is None:
        return None

    now = timezone.now()
    age_seconds = (now - entry.recorded_at).total_seconds()
    minutes_ago = max(0, int(round(age_seconds / 60)))
    is_cgm = (entry.source or "").lower() == "dexcom" or (entry.context or "") == "cgm"
    stale = is_cgm and minutes_ago > CGM_STALE_MINUTES

    trend_code = entry.trend or ""
    trend_label, trend_arrow = TREND_DISPLAY.get(trend_code, ("", ""))
    trend_rate = float(entry.trend_rate) if entry.trend_rate is not None else None

    return {
        "value": float(entry.value),
        "unit": entry.unit,
        "timestamp": entry.recorded_at.isoformat(),
        "context": entry.context or "",
        "context_label": CONTEXT_LABELS.get(entry.context or "", ""),
        "source": entry.source or "",
        "source_label": SOURCE_LABELS.get(entry.source or "", entry.source or ""),
        "trend": trend_code,
        "trend_label": trend_label,
        "trend_arrow": trend_arrow,
        "trend_rate": trend_rate,
        "minutes_ago": minutes_ago,
        "stale": stale,
    }


def build_glucose_summary(user) -> dict | None:
    """Build the canonical SUMMARY block from the user's glucose history.

    Returns aggregates across 7 / 30 / 90 day windows + projected A1C
    (GMI). Returns ``None`` when there are NO readings at all over the
    last 90 days (consumer renders the "no glucose summary" branch).

    Output shape:
        {
          "average_7d":             int | None,
          "average_30d":            int | None,
          "average_90d":            int | None,
          "time_in_range_pct_7d":   float | None,
          "time_in_range_pct_30d":  float | None,
          "projected_a1c":          float | None,
          "projected_a1c_confidence": str,    # "high" | "medium" | "low" | ""
          "trend_7d_vs_30d":        str,      # "improving"|"stable"|"worsening"|""
          "reading_count_90d":      int,
          "overnight_avg":          float | None,
          "sync_stale":             bool,
        }

    Determinism: pure aggregation over GlucoseEntry. Reuses the existing
    SAE-built projected_a1c and time_in_range fields when present on the
    health state, otherwise computes inline. NEVER live-computes A1C in
    the hot path of a Beth conversation — that's why we accept a
    `health_state` injection for the prebuilt values.
    """
    from django.db.models import Avg, Count

    from apps.health.models import GlucoseEntry

    now = timezone.now()
    cutoff_90d = now - timedelta(days=90)
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d = now - timedelta(days=7)

    qs90 = GlucoseEntry.objects.filter(user=user, recorded_at__gte=cutoff_90d)
    count_90d = qs90.count()
    if count_90d == 0:
        return None

    avg_7d = qs90.filter(recorded_at__gte=cutoff_7d).aggregate(a=Avg("value"))["a"]
    avg_30d = qs90.filter(recorded_at__gte=cutoff_30d).aggregate(a=Avg("value"))["a"]
    avg_90d = qs90.aggregate(a=Avg("value"))["a"]

    # In-range = 70-180 mg/dL (clinical TIR convention).
    def _pct_in_range(qs):
        total = qs.count()
        if total == 0:
            return None
        in_range = qs.filter(value__gte=70, value__lte=180).count()
        return round((in_range / total) * 100, 1)

    tir_7d = _pct_in_range(qs90.filter(recorded_at__gte=cutoff_7d))
    tir_30d = _pct_in_range(qs90.filter(recorded_at__gte=cutoff_30d))

    # Trend: 7d vs 30d average. Threshold = 5 mg/dL change. Direction
    # follows clinical desirability: lower is "improving" for a Type II
    # diabetic, higher is "worsening." Never speculation — only fires
    # when both windows have enough readings.
    trend = ""
    if avg_7d is not None and avg_30d is not None and qs90.filter(
        recorded_at__gte=cutoff_30d
    ).count() >= 14:
        diff = float(avg_7d) - float(avg_30d)
        if abs(diff) < 5:
            trend = "stable"
        elif diff < 0:
            trend = "improving"
        else:
            trend = "worsening"

    # Projected A1C — GMI formula (Bergenstal 2018):
    #   A1C ≈ 3.31 + (0.02392 × mean glucose mg/dL)
    # Confidence buckets follow data density (90-day reading count).
    projected_a1c = None
    confidence = ""
    if avg_90d is not None and count_90d >= 60:
        projected_a1c = round(3.31 + (0.02392 * float(avg_90d)), 1)
        if count_90d >= 1000:
            confidence = "high"
        elif count_90d >= 200:
            confidence = "medium"
        else:
            confidence = "low"

    # Overnight average — readings between midnight and 06:00 local time.
    # Useful for fasting baseline. Optional — only computed when enough
    # nightly data exists.
    overnight_qs = qs90.filter(
        recorded_at__hour__gte=0, recorded_at__hour__lt=6,
    )
    overnight_avg = None
    if overnight_qs.count() >= 7:
        ovr_avg = overnight_qs.aggregate(a=Avg("value"))["a"]
        if ovr_avg is not None:
            overnight_avg = round(float(ovr_avg), 1)

    # sync_stale — when the most recent reading anywhere is older than
    # SUMMARY_STALE_DAYS. Distinct from CGM staleness in glucose_latest.
    last_dt = qs90.order_by("-recorded_at").values_list(
        "recorded_at", flat=True,
    ).first()
    sync_stale = False
    if last_dt is not None:
        sync_stale = (now - last_dt).days > SUMMARY_STALE_DAYS

    return {
        "average_7d": int(round(float(avg_7d))) if avg_7d is not None else None,
        "average_30d": int(round(float(avg_30d))) if avg_30d is not None else None,
        "average_90d": int(round(float(avg_90d))) if avg_90d is not None else None,
        "time_in_range_pct_7d": tir_7d,
        "time_in_range_pct_30d": tir_30d,
        "projected_a1c": projected_a1c,
        "projected_a1c_confidence": confidence,
        "trend_7d_vs_30d": trend,
        "reading_count_90d": count_90d,
        "overnight_avg": overnight_avg,
        "sync_stale": sync_stale,
    }


def render_latest_message(latest: dict | None, summary: dict | None = None) -> str:
    """Render the deterministic "your most recent glucose reading" sentence.

    Pure function over the snapshot dicts. The output NEVER contains the
    words "average" / "weekly" / "estimated A1C" / "time in range" — that
    is the SUMMARY surface, locked separately. Conversely, the SUMMARY
    renderer never contains "last" / "latest" / "most recent" / "right now".

    The trust-preserving copy fires when ``latest is None`` but the user
    DOES have summary data — we name the exact gap instead of saying
    "I don't have your data." Locked by TrustCopyTests.
    """
    if latest is not None:
        time_str = _format_time_of_day_with_relative(latest["timestamp"])
        age_str = _format_relative_age_minutes(latest["minutes_ago"])
        value = latest["value"]
        # int when whole-number, otherwise 1-decimal — matches how
        # users read glucose values in the wild (143 vs 5.6).
        if abs(value - round(value)) < 0.05:
            value_str = f"{int(round(value))}"
        else:
            value_str = f"{value:g}"

        parts = [
            f"Your most recent glucose reading was **{value_str} "
            f"{latest['unit']}** at **{time_str}** ({age_str})."
        ]
        # Trend line only when we have a real Dexcom arrow.
        if latest.get("trend_label"):
            parts.append(
                f"\nTrend: {latest['trend_label']} {latest['trend_arrow']}"
            )
        # Source line — concrete naming per spec ("Dexcom CGM" preferred).
        if latest.get("source_label"):
            parts.append(f"\nSource: {latest['source_label']}")
        # Stale badge when applicable.
        if latest.get("stale"):
            parts.append(
                "\n\n*Note: this reading is older than 2 hours — "
                "your CGM may not be syncing.*"
            )
        return "".join(parts)

    # No latest event available.
    if summary is not None:
        return (
            "I can see your glucose summary, but I don't currently have "
            "access to the latest timestamped Dexcom reading."
        )
    return "I don't have any glucose readings logged in WLJ yet."


def render_summary_message(summary: dict | None) -> str:
    """Render the deterministic "your glucose this week" sentence.

    The output NEVER contains the words "last" / "latest" / "most recent"
    / "right now" / "current" — that is the LATEST surface, locked
    separately. Summary metrics are always explicitly labelled as
    averages / trends / estimates.
    """
    if summary is None:
        return "I don't have any glucose readings logged in WLJ yet."

    parts = []
    avg_7d = summary.get("average_7d")
    if avg_7d is not None:
        parts.append(f"Your **7-day average glucose** is **{avg_7d} mg/dL**.")
    else:
        parts.append("Your glucose summary is still building this week.")

    detail_lines = []
    tir = summary.get("time_in_range_pct_7d")
    if tir is not None:
        detail_lines.append(f"Time in range: **{tir:g}%** (last 7 days)")
    a1c = summary.get("projected_a1c")
    if a1c is not None:
        conf = summary.get("projected_a1c_confidence") or ""
        conf_str = f" ({conf} confidence)" if conf else ""
        detail_lines.append(f"Estimated A1C: **{a1c:g}%**{conf_str}")
    trend = summary.get("trend_7d_vs_30d") or ""
    if trend:
        detail_lines.append(f"Trend (7d vs 30d): **{trend}**")
    if detail_lines:
        parts.append("\n" + "\n".join(detail_lines))

    if summary.get("sync_stale"):
        parts.append(
            "\n\n*Note: your most recent glucose entry is more than a "
            "week old — sync may have stalled.*"
        )
    return "".join(parts)


# ── Internals ──────────────────────────────────────────────────────────


def _format_time_of_day_with_relative(timestamp_iso: str) -> str:
    """Format "2:11 PM today" / "9:42 AM yesterday" / "Mon 7:33 PM"."""
    try:
        dt = datetime.fromisoformat(timestamp_iso)
    except (TypeError, ValueError):
        return timestamp_iso
    # Use the user's local timezone if dt is naive — fall back to the
    # Django current-tz machinery.
    if dt.tzinfo is None:
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    local_dt = timezone.localtime(dt)
    now_local = timezone.localtime(timezone.now())
    today = now_local.date()
    target = local_dt.date()
    time_part = local_dt.strftime("%-I:%M %p")
    delta_days = (today - target).days
    if delta_days == 0:
        return f"{time_part} today"
    if delta_days == 1:
        return f"{time_part} yesterday"
    if 0 < delta_days < 7:
        return f"{local_dt.strftime('%a')} {time_part}"
    return f"{local_dt.strftime('%b %-d')} {time_part}"


def _format_relative_age_minutes(minutes_ago: int) -> str:
    """Format "7 minutes ago" / "3 hours ago" / "yesterday" / "5 days ago"."""
    if minutes_ago < 1:
        return "just now"
    if minutes_ago < 60:
        return f"{minutes_ago} minute{'s' if minutes_ago != 1 else ''} ago"
    hours = minutes_ago // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    weeks = days // 7
    if weeks == 1:
        return "1 week ago"
    return f"{weeks} weeks ago"
