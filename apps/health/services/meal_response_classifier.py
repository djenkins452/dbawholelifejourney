"""
MealGlucoseResponse classifier (Phase 1A · C8).

Deterministic, eligibility-gated, lookup-table classification of the
post-meal glucose response. No ML, no inference.

Architecture commitments (from the Phase 0 lock):

* The classifier is invoked explicitly — never via signal handlers.
  Backfill via the C8 management command; runtime triggers in a
  separate commit so the integration path is auditable.
* Confounded meals are excluded by eligibility gates rather than
  classified with low confidence. We'd rather classify fewer meals
  correctly than more meals dubiously.
* Output rows are immutable: re-running the classifier on the same
  FoodEntry is a no-op (returns the existing row).

Eligibility gates (all must pass):

1. FoodEntry.logged_time must be non-null (need a precise timestamp).
2. Baseline CGM reading must exist in the -10m..+5m window.
3. At least 3 of 4 post-meal windows (+30m, +60m, +90m, +120m) must
   contain ≥1 CGM reading.
4. No other FoodEntry in the user's last 90 minutes before the meal
   (clean baseline).
5. No WorkoutSession with started_at in -30m..+120m (exercise confounds
   glucose response).

Classification (lookup, deterministic):

* minimal_spike   — delta_peak < 30 mg/dL
* moderate_spike  — 30 ≤ delta_peak < 60
* large_spike     — 60 ≤ delta_peak < 100
* extreme_spike   — delta_peak ≥ 100
* prolonged_spike — any of the above where delta_2h ≥ 40
  (failed to return to baseline)

The classifier always converts glucose values to mg/dL for consistency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

from django.db import transaction
from django.utils import timezone


logger = logging.getLogger(__name__)


# ── Eligibility / classification constants ──────────────────────────


BASELINE_WINDOW_BEFORE_MIN = 10
BASELINE_WINDOW_AFTER_MIN = 5
POST_MEAL_WINDOW_MIN = 120
POST_MEAL_CHECK_OFFSETS_MIN = (30, 60, 90, 120)
MIN_POST_MEAL_WINDOWS_REQUIRED = 3
PRIOR_MEAL_EXCLUSION_MIN = 90
WORKOUT_EXCLUSION_BEFORE_MIN = 30
WORKOUT_EXCLUSION_AFTER_MIN = 120

# Classification thresholds (mg/dL).
SPIKE_MINIMAL_MAX = 30
SPIKE_MODERATE_MAX = 60
SPIKE_LARGE_MAX = 100
PROLONGED_DELTA_2H_MIN = 40


class ClassifierResult:
    """Why the classifier did what it did. Used by the backfill command
    for reporting and by tests for behavior assertions."""

    OK = "classified"
    SKIPPED_NO_TIME = "skipped:no_logged_time"
    SKIPPED_NO_BASELINE = "skipped:no_baseline_reading"
    SKIPPED_INSUFFICIENT_POST_MEAL = "skipped:insufficient_post_meal_readings"
    SKIPPED_PRIOR_MEAL = "skipped:prior_meal_within_90min"
    SKIPPED_WORKOUT_IN_WINDOW = "skipped:workout_in_window"
    SKIPPED_ALREADY_CLASSIFIED = "skipped:already_classified"


@dataclass
class _Reading:
    when: datetime
    value_mg_dl: float


def _to_mg_dl(value: Decimal, unit: str) -> float:
    """Normalize glucose unit. mmol/L → mg/dL via the standard factor."""
    val = float(value)
    if unit == "mmol/L":
        return val * 18.0
    return val


def _glucose_readings_in_window(
    user, start: datetime, end: datetime,
) -> List[_Reading]:
    from apps.health.models import GlucoseEntry

    qs = GlucoseEntry.objects.filter(
        user=user,
        recorded_at__gte=start,
        recorded_at__lt=end,
    ).order_by("recorded_at")
    return [
        _Reading(when=r.recorded_at, value_mg_dl=_to_mg_dl(r.value, r.unit))
        for r in qs
    ]


def _resolve_meal_consumed_at(food_entry) -> Optional[datetime]:
    """Compose FoodEntry.logged_date + logged_time into a timezone-aware
    datetime. Returns None when logged_time is missing."""
    if food_entry.logged_time is None:
        return None
    naive = datetime.combine(food_entry.logged_date, food_entry.logged_time)
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def _classify_label(delta_peak: float, delta_2h: float) -> str:
    """Lookup-table classification. No ML, no inference."""
    from apps.health.models import MealGlucoseResponse

    if delta_peak < SPIKE_MINIMAL_MAX:
        base = MealGlucoseResponse.CLASS_MINIMAL_SPIKE
    elif delta_peak < SPIKE_MODERATE_MAX:
        base = MealGlucoseResponse.CLASS_MODERATE_SPIKE
    elif delta_peak < SPIKE_LARGE_MAX:
        base = MealGlucoseResponse.CLASS_LARGE_SPIKE
    else:
        base = MealGlucoseResponse.CLASS_EXTREME_SPIKE
    if delta_2h >= PROLONGED_DELTA_2H_MIN:
        return MealGlucoseResponse.CLASS_PROLONGED_SPIKE
    return base


# ── Public API ──────────────────────────────────────────────────────


def classify_meal_glucose_response(food_entry, force: bool = False):
    """
    Classify the post-meal glucose response for a single FoodEntry.

    Returns the (MealGlucoseResponse | None, status_string) tuple. The
    status string is one of the ClassifierResult constants. None means
    no row was created/returned (skipped via an eligibility gate).
    """
    from apps.health.models import (
        FoodEntry,
        MealGlucoseResponse,
        WorkoutSession,
    )

    if not isinstance(food_entry, FoodEntry):
        raise TypeError("classify_meal_glucose_response requires a FoodEntry")

    # Gate 0: already classified? (idempotent unless forced)
    existing = (
        MealGlucoseResponse.objects.filter(food_entry=food_entry).first()
    )
    if existing and not force:
        return existing, ClassifierResult.SKIPPED_ALREADY_CLASSIFIED

    # Gate 1: precise timestamp.
    meal_at = _resolve_meal_consumed_at(food_entry)
    if meal_at is None:
        return None, ClassifierResult.SKIPPED_NO_TIME

    user = food_entry.user

    # Gate 4: no other meal in the prior 90 minutes.
    prior_meal_window_start = meal_at - timedelta(minutes=PRIOR_MEAL_EXCLUSION_MIN)
    prior_exists = (
        FoodEntry.objects
        .filter(
            user=user,
            logged_date__in=(meal_at.date(), prior_meal_window_start.date()),
        )
        .exclude(pk=food_entry.pk)
        .exclude(logged_time__isnull=True)
    )
    for other in prior_exists:
        other_at = _resolve_meal_consumed_at(other)
        if other_at is None:
            continue
        if prior_meal_window_start <= other_at < meal_at:
            return None, ClassifierResult.SKIPPED_PRIOR_MEAL

    # Gate 5: no workout in the -30m..+120m window.
    workout_window_start = meal_at - timedelta(minutes=WORKOUT_EXCLUSION_BEFORE_MIN)
    workout_window_end = meal_at + timedelta(minutes=WORKOUT_EXCLUSION_AFTER_MIN)
    workout_present = WorkoutSession.objects.filter(
        user=user,
        started_at__gte=workout_window_start,
        started_at__lt=workout_window_end,
    ).exists()
    if workout_present:
        return None, ClassifierResult.SKIPPED_WORKOUT_IN_WINDOW

    # Pull all CGM readings spanning baseline + post-meal in one query.
    overall_start = meal_at - timedelta(minutes=BASELINE_WINDOW_BEFORE_MIN)
    overall_end = meal_at + timedelta(minutes=POST_MEAL_WINDOW_MIN + 5)
    readings = _glucose_readings_in_window(user, overall_start, overall_end)
    if not readings:
        return None, ClassifierResult.SKIPPED_NO_BASELINE

    # Gate 2: baseline reading in -10m..+5m.
    baseline_window_start = meal_at - timedelta(minutes=BASELINE_WINDOW_BEFORE_MIN)
    baseline_window_end = meal_at + timedelta(minutes=BASELINE_WINDOW_AFTER_MIN)
    baseline_readings = [
        r for r in readings
        if baseline_window_start <= r.when <= baseline_window_end
    ]
    if not baseline_readings:
        return None, ClassifierResult.SKIPPED_NO_BASELINE
    # Use the reading nearest to meal_at as the baseline.
    baseline_readings.sort(key=lambda r: abs((r.when - meal_at).total_seconds()))
    baseline_reading = baseline_readings[0]

    # Gate 3: ≥3 of 4 post-meal windows have a reading.
    post_meal_readings = [r for r in readings if r.when > meal_at]
    windows_with_data = 0
    for offset in POST_MEAL_CHECK_OFFSETS_MIN:
        # ±10-minute tolerance around each check offset.
        win_start = meal_at + timedelta(minutes=offset - 10)
        win_end = meal_at + timedelta(minutes=offset + 10)
        if any(win_start <= r.when <= win_end for r in post_meal_readings):
            windows_with_data += 1
    if windows_with_data < MIN_POST_MEAL_WINDOWS_REQUIRED:
        return None, ClassifierResult.SKIPPED_INSUFFICIENT_POST_MEAL

    # All gates passed — compute features.
    peak_reading = max(post_meal_readings, key=lambda r: r.value_mg_dl)
    # +120m anchor: nearest reading to +120m.
    target_120m = meal_at + timedelta(minutes=120)
    nearest_120m = min(
        post_meal_readings,
        key=lambda r: abs((r.when - target_120m).total_seconds()),
    )

    delta_peak = peak_reading.value_mg_dl - baseline_reading.value_mg_dl
    delta_2h = nearest_120m.value_mg_dl - baseline_reading.value_mg_dl
    time_to_peak = int(
        max(0, (peak_reading.when - meal_at).total_seconds() // 60)
    )
    classification = _classify_label(delta_peak, delta_2h)

    with transaction.atomic():
        obj, created = MealGlucoseResponse.objects.update_or_create(
            food_entry=food_entry,
            defaults=dict(
                user=user,
                meal_consumed_at=meal_at,
                classification=classification,
                baseline_glucose=Decimal(str(round(baseline_reading.value_mg_dl, 2))),
                peak_glucose=Decimal(str(round(peak_reading.value_mg_dl, 2))),
                glucose_at_120m=Decimal(str(round(nearest_120m.value_mg_dl, 2))),
                delta_peak=Decimal(str(round(delta_peak, 2))),
                delta_2h=Decimal(str(round(delta_2h, 2))),
                time_to_peak_min=time_to_peak,
            ),
        )
    return obj, ClassifierResult.OK
