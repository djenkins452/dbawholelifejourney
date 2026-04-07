"""
Phase 3 — Signal Trust Contract (single shared service).

Every state builder calls into this module to attach a Trust Report to its
output. A Trust Report describes how much weight CoS / dashboards / CDCE
should give a signal:

    {
        "value":         <canonical headline value>,
        "confidence":    0..100,                    # how certain
        "sufficiency":   "low" | "medium" | "high",  # is there enough data?
        "last_updated":  ISO string or None,
        "source_count":  int,                        # how many records
        "priority_level": "low" | "medium" | "high", # how urgent
        "priority_reason": str,                      # why
    }

DESIGN RULES (Phase 3):
    1. Trust lives in state, not in CoS. CoS reads, never computes.
    2. Trust is ADDITIVE — it never removes existing state fields.
    3. Each assessor receives the already-computed domain state dict so we
       do not double-query the DB.
    4. None ≠ 0 (Phase 1 rule still applies). Sufficiency is the gate; if
       sufficiency is "low" the value may still be present but downstream
       consumers should treat it as advisory.
    5. The shape is intentionally simple — flat dict, primitive values —
       so the LLM can read it without complex parsing.

The assessors return ``None`` when the domain has no data at all — that
"absence of trust" is itself a signal that nothing has ever been logged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Sufficiency thresholds (Phase 3 canonical) ──────────────────────
# Each tuple is (high_min, medium_min) — values below medium_min are "low".
SUFFICIENCY_THRESHOLDS = {
    "body_composition": (3, 1),   # entries in last 14 days
    "workouts": (5, 1),           # sessions in last 7 days
    "nutrition": (5, 3),          # days logged in last 7 days
    "medication": (5, 1),         # days with at least one log in last 7 days
    "fasting": (3, 1),            # completed fasts in last 7 days
    "sleep": (5, 3),              # sleep entries in last 7 days
    "journal": (4, 2),            # entries in last 7 days
    "faith": (5, 1),              # reading streak days
}


# ── Helpers ──────────────────────────────────────────────────────────


def _classify_sufficiency(domain: str, source_count: Optional[int]) -> str:
    """Map a raw entry count to low/medium/high using domain thresholds."""
    if source_count is None or source_count <= 0:
        return "low"
    high_min, medium_min = SUFFICIENCY_THRESHOLDS.get(domain, (5, 2))
    if source_count >= high_min:
        return "high"
    if source_count >= medium_min:
        return "medium"
    return "low"


def _confidence_from(
    *,
    source_count: int,
    days_since_update: Optional[float],
    target_count: int = 5,
    fresh_window_days: float = 1.0,
    stale_window_days: float = 7.0,
) -> int:
    """
    Compute confidence (0-100) from data density and freshness.

    base 50
      + up to 30 points for entry density (source_count / target_count)
      + up to 20 points for freshness:
          - within fresh_window: full +20
          - within stale_window: linear decay
          - older: -20 (penalty for stale data)
    """
    if source_count is None or source_count <= 0:
        return 0

    density_bonus = min(source_count / max(target_count, 1), 1.0) * 30

    freshness_bonus: float
    if days_since_update is None:
        # We have data but no timestamp — assume stale.
        freshness_bonus = -10
    elif days_since_update <= fresh_window_days:
        freshness_bonus = 20
    elif days_since_update >= stale_window_days:
        freshness_bonus = -20
    else:
        # Linear decay from 20 to 0 over (fresh, stale)
        span = stale_window_days - fresh_window_days
        progress = (days_since_update - fresh_window_days) / span
        freshness_bonus = 20 - (progress * 20)

    score = 50 + density_bonus + freshness_bonus
    return max(0, min(100, int(round(score))))


def _days_since(iso_or_dt) -> Optional[float]:
    """Return days elapsed since an ISO string / datetime, or None."""
    if iso_or_dt is None:
        return None
    if isinstance(iso_or_dt, str):
        try:
            iso = iso_or_dt.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso)
        except (ValueError, TypeError):
            return None
    elif isinstance(iso_or_dt, datetime):
        dt = iso_or_dt
    else:
        return None
    try:
        from django.utils import timezone
        now = timezone.now()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        return max(0.0, (now - dt).total_seconds() / 86400)
    except Exception:
        return None


def _build_report(
    *,
    value: Any,
    sufficiency: str,
    confidence: int,
    last_updated: Any,
    source_count: int,
    priority_level: str,
    priority_reason: str,
) -> Dict[str, Any]:
    """Assemble the canonical Trust Report dict."""
    return {
        "value": value,
        "confidence": confidence,
        "sufficiency": sufficiency,
        "last_updated": last_updated,
        "source_count": source_count,
        "priority_level": priority_level,
        "priority_reason": priority_reason,
    }


# ── Per-domain assessors ─────────────────────────────────────────────
# Every assessor takes (user, state_dict) and returns a Trust Report or None.
# State is the dict already computed by the corresponding build_*_state.


def assess_body_composition(user, health_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for body composition (uses body_fat_pct as headline)."""
    value = health_state.get("body_fat_current")
    last_updated = health_state.get("last_body_fat_entry")
    if value is None and not last_updated:
        return None

    # Count entries in the last 14 days for sufficiency.
    try:
        from apps.health.models import BodyCompositionEntry
        from django.utils import timezone
        cutoff = (timezone.now() - timedelta(days=14)).date()
        source_count = BodyCompositionEntry.objects.filter(
            user=user,
            metric_name="body_fat_pct",
            measurement_date__gte=cutoff,
            status="active",
        ).count()
    except Exception as e:
        logger.warning("trust: body_comp source_count failed: %s", e)
        source_count = 1 if value is not None else 0

    days_since = _days_since(last_updated)
    sufficiency = _classify_sufficiency("body_composition", source_count)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=4,
        fresh_window_days=2,
        stale_window_days=14,
    )

    # Priority: based on plateau / muscle loss risk if available.
    plateau = health_state.get("plateau_risk_label")
    muscle_risk = health_state.get("muscle_loss_risk_level")
    if plateau == "HIGH" or muscle_risk == "HIGH":
        priority_level = "high"
        priority_reason = (
            f"Plateau risk {plateau or 'unknown'}, muscle loss risk {muscle_risk or 'unknown'}"
        )
    elif plateau == "RISING" or muscle_risk == "MED":
        priority_level = "medium"
        priority_reason = "Trends warrant attention"
    elif sufficiency == "low":
        priority_level = "medium"
        priority_reason = "Need more measurements to detect trends"
    else:
        priority_level = "low"
        priority_reason = "Tracking on plan"

    return _build_report(
        value=value,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_updated,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_workouts(user, fitness_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for workouts. Headline = workout_adherence_score."""
    workouts_7d = fitness_state.get("workouts_7d", 0) or 0
    expected_7d = fitness_state.get("workout_expected_7d") or 0
    completed_7d = fitness_state.get("workout_completed_7d") or workouts_7d
    missed_7d = fitness_state.get("workout_missed_7d") or 0
    adherence = fitness_state.get("workout_adherence_score")
    last_workout = fitness_state.get("last_workout_date")

    if workouts_7d == 0 and expected_7d == 0 and last_workout is None:
        return None

    source_count = workouts_7d
    sufficiency = _classify_sufficiency("workouts", source_count)
    days_since = _days_since(last_workout)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=5,
        fresh_window_days=2,
        stale_window_days=10,
    )

    # Priority: based on adherence + missed sessions
    if expected_7d and missed_7d >= 3:
        priority_level = "high"
        priority_reason = f"{missed_7d} of {expected_7d} planned sessions missed this week"
    elif adherence is not None and adherence < 50:
        priority_level = "high"
        priority_reason = f"Adherence at {adherence}% — well below plan"
    elif adherence is not None and adherence < 80:
        priority_level = "medium"
        priority_reason = f"Adherence at {adherence}% — slipping"
    elif workouts_7d == 0 and expected_7d > 0:
        priority_level = "high"
        priority_reason = f"No workouts logged this week against plan of {expected_7d}"
    elif sufficiency == "low":
        priority_level = "medium"
        priority_reason = "Limited workout data this week"
    else:
        priority_level = "low"
        priority_reason = "On plan"

    return _build_report(
        value=adherence if adherence is not None else workouts_7d,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_workout,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_nutrition(user, nutrition_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for nutrition. Headline = macro_compliance_score."""
    food_entries_7d = nutrition_state.get("food_entries_7d", 0) or 0
    macro_score = nutrition_state.get("macro_compliance_score")
    cal_today = nutrition_state.get("daily_calories")
    cal_target = nutrition_state.get("calorie_target")
    last_food = nutrition_state.get("last_food_entry")

    if food_entries_7d == 0 and cal_today is None and last_food is None:
        return None

    # Sufficiency is "days with at least one logged entry in the last 7d".
    # We approximate from food_entries_7d (entry count, not day count).
    # Conservative: if entries_7d < 3 we say low; ≥ 5 high.
    source_count = food_entries_7d
    sufficiency = _classify_sufficiency("nutrition", source_count)
    days_since = _days_since(last_food)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=7,
        fresh_window_days=1,
        stale_window_days=4,
    )

    # Priority: how far off calorie / macro targets are
    if macro_score is not None and macro_score < 50:
        priority_level = "high"
        priority_reason = f"Macro compliance at {macro_score}/100"
    elif cal_target and cal_today is not None:
        delta_pct = abs((cal_today - cal_target) / cal_target * 100) if cal_target else 0
        if delta_pct > 25:
            priority_level = "high"
            priority_reason = f"Calories {int(delta_pct)}% off target today"
        elif delta_pct > 12:
            priority_level = "medium"
            priority_reason = f"Calories {int(delta_pct)}% off target today"
        else:
            priority_level = "low"
            priority_reason = "On target"
    elif sufficiency == "low":
        priority_level = "medium"
        priority_reason = "Need more days logged for trustworthy guidance"
    else:
        priority_level = "low"
        priority_reason = "Tracking on plan"

    return _build_report(
        value=macro_score if macro_score is not None else cal_today,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_food,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_medication(user, med_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for medication adherence."""
    active_count = med_state.get("active_count", 0) or 0
    if active_count == 0:
        return None

    adherence_7d = med_state.get("adherence_7d")
    expected_7d = med_state.get("expected_7d") or 0
    completed_7d = med_state.get("completed_7d") or 0
    missed_7d = med_state.get("missed_7d") or 0
    today_taken = med_state.get("today_taken", 0) or 0
    today_missed = med_state.get("today_missed", 0) or 0
    expected_today = med_state.get("expected_today", 0) or 0

    # Sufficiency: how many days had at least one logged dose this week.
    # Approximate via completed_7d count vs expected_7d.
    source_count = completed_7d if completed_7d else today_taken
    sufficiency = _classify_sufficiency("medication", source_count)

    # Confidence: recency is "today" — high if any dose logged today, lower if not.
    if today_taken > 0 or today_missed > 0:
        days_since = 0.0
    else:
        days_since = 1.5  # No log today
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=expected_7d if expected_7d else 7,
        fresh_window_days=1,
        stale_window_days=4,
    )

    # Priority
    if expected_today and today_missed > 0 and today_taken == 0:
        priority_level = "high"
        priority_reason = f"{today_missed} of {expected_today} doses missed today"
    elif adherence_7d is not None and adherence_7d < 0.7:
        priority_level = "high"
        priority_reason = f"7-day adherence at {round(adherence_7d * 100)}%"
    elif missed_7d >= 3:
        priority_level = "medium"
        priority_reason = f"{missed_7d} doses missed this week"
    elif adherence_7d is not None and adherence_7d < 0.9:
        priority_level = "medium"
        priority_reason = f"7-day adherence at {round(adherence_7d * 100)}%"
    else:
        priority_level = "low"
        priority_reason = "On schedule"

    headline = (
        round(adherence_7d * 100, 1) if adherence_7d is not None else today_taken
    )

    return _build_report(
        value=headline,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=None,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_fasting(user, fasting_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for fasting. Returns None when domain disabled."""
    if not fasting_state.get("enabled", False):
        return None

    fasts_7d = fasting_state.get("fasts_7d", 0) or 0
    compliance = fasting_state.get("fasting_compliance_score")
    last_end = fasting_state.get("last_fast_end")
    current_active = fasting_state.get("current_fast_active", False)

    source_count = fasts_7d
    sufficiency = _classify_sufficiency("fasting", source_count)
    days_since = 0.0 if current_active else _days_since(last_end)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=4,
        fresh_window_days=2,
        stale_window_days=7,
    )

    if compliance is None and fasts_7d == 0:
        priority_level = "high"
        priority_reason = "Fasting enabled but no fasts logged this week"
    elif compliance is not None and compliance < 50:
        priority_level = "high"
        priority_reason = f"Fasting compliance at {compliance}%"
    elif compliance is not None and compliance < 80:
        priority_level = "medium"
        priority_reason = f"Fasting compliance at {compliance}%"
    else:
        priority_level = "low"
        priority_reason = "On protocol"

    return _build_report(
        value=compliance,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_end,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_sleep(user, health_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for sleep using health_state sleep fields."""
    avg_7d = (
        health_state.get("sleep_avg_hours_7d")
        or health_state.get("sleep_avg_duration_7d")
    )
    consistency = health_state.get("sleep_consistency_score")
    good_nights = health_state.get("sleep_good_nights_7d")
    last_entry = health_state.get("last_sleep_entry")
    entries_7d = health_state.get("sleep_entries_7d") or 0

    if avg_7d is None and entries_7d == 0 and last_entry is None:
        return None

    source_count = entries_7d
    sufficiency = _classify_sufficiency("sleep", source_count)
    days_since = _days_since(last_entry)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since,
        target_count=7,
        fresh_window_days=1.5,
        stale_window_days=4,
    )

    # Priority: poor sleep = high
    if avg_7d is not None and avg_7d < 6:
        priority_level = "high"
        priority_reason = f"Averaging {round(float(avg_7d), 1)}h — well below 7h"
    elif good_nights is not None and good_nights <= 2:
        priority_level = "high"
        priority_reason = f"Only {good_nights} good nights this week"
    elif avg_7d is not None and avg_7d < 7:
        priority_level = "medium"
        priority_reason = f"Averaging {round(float(avg_7d), 1)}h"
    elif sufficiency == "low":
        priority_level = "medium"
        priority_reason = "Limited sleep data this week"
    else:
        priority_level = "low"
        priority_reason = "Sleeping well"

    return _build_report(
        value=avg_7d,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_entry,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_journal(user, journal_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for journaling activity. Light version per Phase 3."""
    entries_7d = journal_state.get("entries_7d", 0) or 0
    last_entry = journal_state.get("last_entry")
    days_since = journal_state.get("days_since_entry")
    mood_avg = journal_state.get("mood_avg_7d")

    if entries_7d == 0 and last_entry is None:
        return None

    source_count = entries_7d
    sufficiency = _classify_sufficiency("journal", source_count)
    days_since_freshness = float(days_since) if days_since is not None else _days_since(last_entry)
    confidence = _confidence_from(
        source_count=source_count,
        days_since_update=days_since_freshness,
        target_count=5,
        fresh_window_days=2,
        stale_window_days=7,
    )

    if days_since is not None and days_since >= 7:
        priority_level = "high"
        priority_reason = f"{days_since} days since last journal entry"
    elif mood_avg is not None and mood_avg <= 2.5:
        priority_level = "high"
        priority_reason = f"7-day mood average {round(float(mood_avg), 1)}/5"
    elif days_since is not None and days_since >= 3:
        priority_level = "medium"
        priority_reason = f"{days_since} days since last entry"
    else:
        priority_level = "low"
        priority_reason = "Journaling consistently"

    return _build_report(
        value=mood_avg if mood_avg is not None else entries_7d,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_entry,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )


def assess_faith(user, faith_state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Trust report for faith reading practice. Light version per Phase 3."""
    streak = faith_state.get("reading_streak", 0) or 0
    days_since = faith_state.get("days_since_reading")
    last_read = faith_state.get("last_scripture_read")
    active_plans = faith_state.get("active_reading_plans", 0) or 0

    if streak == 0 and last_read is None and active_plans == 0:
        return None

    source_count = streak
    sufficiency = _classify_sufficiency("faith", source_count)
    days_since_freshness = (
        float(days_since) if days_since is not None else _days_since(last_read)
    )
    confidence = _confidence_from(
        source_count=streak,
        days_since_update=days_since_freshness,
        target_count=7,
        fresh_window_days=2,
        stale_window_days=7,
    )

    if days_since is not None and days_since >= 7:
        priority_level = "high"
        priority_reason = f"{days_since} days since last scripture reading"
    elif days_since is not None and days_since >= 3:
        priority_level = "medium"
        priority_reason = f"{days_since} days since last reading"
    elif streak == 0 and active_plans > 0:
        priority_level = "medium"
        priority_reason = "Active reading plan but no recent progress"
    else:
        priority_level = "low"
        priority_reason = "Reading consistently"

    return _build_report(
        value=streak,
        sufficiency=sufficiency,
        confidence=confidence,
        last_updated=last_read,
        source_count=source_count,
        priority_level=priority_level,
        priority_reason=priority_reason,
    )
