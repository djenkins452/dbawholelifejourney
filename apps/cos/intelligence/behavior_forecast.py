"""
COS-CX6: Behavioral Forecast Extension
=======================================

Predicts probability of completing key behaviors based on historical
patterns, schedule load, and pressure level.

"Workout completion probability tomorrow: 28%. Heavy meeting load detected."

This extends the Drift Engine concept with historical behavioral
correlation — on heavy schedule days, which behaviors get dropped?

Performance target: < 20ms (batch queries, no per-day DB hits).
Token budget: ~100 tokens max.
"""
import logging
from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate

logger = logging.getLogger(__name__)

MAX_FORECAST_ITEMS = 3
LOOKBACK_WEEKS = 8  # 8-week history for pattern detection


def compute_behavior_forecast(user, now, cos_context=None):
    """
    Predict probability of completing key behaviors tomorrow.

    Uses historical completion rates segmented by schedule load
    (light day vs. heavy day) and current conditions.

    Optimized: uses batch queries instead of per-day exists() calls.
    Total DB queries: ~6 (vs. ~224 in the original implementation).

    Args:
        user: Django User object
        now: timezone-aware datetime in user's timezone
        cos_context: optional dict from build_cos_context()

    Returns:
        str — formatted forecast block, or "" if insufficient data.
    """
    try:
        today = now.date()
        tomorrow = today + timedelta(days=1)
        lookback_start = today - timedelta(weeks=LOOKBACK_WEEKS)

        # ── Batch query 1: Tomorrow's schedule load ──────────────
        tomorrow_load = _get_schedule_load(user, tomorrow)

        # ── Batch query 2: All schedule loads in lookback window ──
        daily_loads = _batch_schedule_loads(user, lookback_start, today)

        # ── Batch queries 3-5: All completion dates per behavior ──
        workout_dates = _batch_workout_dates(user, lookback_start, today)
        reading_dates = _batch_reading_dates(user, lookback_start, today)
        journal_dates = _batch_journal_dates(user, lookback_start, today)

        # ── Compute forecasts from pre-fetched data ──────────────
        forecasts = []

        for behavior_name, completion_dates in [
            ("Workout", workout_dates),
            ("Bible Reading", reading_dates),
            ("Journal Entry", journal_dates),
        ]:
            result = _forecast_from_batched_data(
                lookback_start, today, tomorrow_load,
                daily_loads, completion_dates, behavior_name,
            )
            if result:
                forecasts.append(result)

        if not forecasts:
            return ""

        lines = ["=== BEHAVIORAL FORECAST (tomorrow) ==="]
        load_desc = _load_description(tomorrow_load)
        if load_desc:
            lines.append(f"Schedule load: {load_desc}")

        for item in forecasts[:MAX_FORECAST_ITEMS]:
            pct = item['probability']
            name = item['behavior']
            risk_tag = ""
            if pct < 30:
                risk_tag = " [AT RISK]"
            elif pct < 50:
                risk_tag = " [Watch]"

            lines.append(f"  {name}: {pct}% likely{risk_tag}")
            if item.get('note'):
                lines.append(f"    {item['note']}")

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Behavior forecast skipped: %s", e)
        return ""


# ═══════════════════════════════════════════════════════════════════
# Batch query helpers — one query each, covering the entire window
# ═══════════════════════════════════════════════════════════════════

def _get_schedule_load(user, target_date):
    """Classify schedule load for a single date (1 query)."""
    try:
        from apps.calendar_engine.models import CalendarEvent
        count = CalendarEvent.objects.filter(
            user=user,
            start_dt__date=target_date,
            deleted_at__isnull=True,
        ).exclude(status='canceled').count()
        return _count_to_load(count)
    except Exception:
        return 'light'


def _batch_schedule_loads(user, start_date, end_date):
    """
    Get event counts per day for the entire lookback window (1 query).
    Returns: dict[date, str] mapping date -> load level.
    """
    try:
        from apps.calendar_engine.models import CalendarEvent
        daily_counts = (
            CalendarEvent.objects.filter(
                user=user,
                start_dt__date__gte=start_date,
                start_dt__date__lte=end_date,
                deleted_at__isnull=True,
            )
            .exclude(status='canceled')
            .annotate(event_date=TruncDate('start_dt'))
            .values('event_date')
            .annotate(count=Count('id'))
        )
        loads = {}
        for row in daily_counts:
            loads[row['event_date']] = _count_to_load(row['count'])
        return loads
    except Exception:
        return {}


def _batch_workout_dates(user, start_date, end_date):
    """Get all dates with completed workouts (1 query)."""
    try:
        from apps.health.services.workout_queries import WorkoutQueries
        return set(
            WorkoutQueries.completed_in_range(
                user, start_date, end_date,
            ).values_list('date', flat=True).distinct()
        )
    except Exception:
        return set()


def _batch_reading_dates(user, start_date, end_date):
    """Get all dates with reading plan completions (1 query)."""
    try:
        from apps.faith.models import UserReadingProgress
        return set(
            UserReadingProgress.objects.filter(
                user_plan__user=user,
                completed_at__date__gte=start_date,
                completed_at__date__lte=end_date,
            )
            .annotate(comp_date=TruncDate('completed_at'))
            .values_list('comp_date', flat=True)
            .distinct()
        )
    except Exception:
        return set()


def _batch_journal_dates(user, start_date, end_date):
    """Get all dates with journal entries (1 query)."""
    try:
        from apps.journal.models import JournalEntry
        return set(
            JournalEntry.objects.filter(
                user=user,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )
            .annotate(entry_date=TruncDate('created_at'))
            .values_list('entry_date', flat=True)
            .distinct()
        )
    except Exception:
        return set()


# ═══════════════════════════════════════════════════════════════════
# Forecast computation (pure Python, no DB queries)
# ═══════════════════════════════════════════════════════════════════

def _forecast_from_batched_data(
    lookback_start, today, tomorrow_load,
    daily_loads, completion_dates, behavior_name,
):
    """
    Compute forecast from pre-fetched batch data (zero DB queries).

    Args:
        lookback_start: date — start of lookback window
        today: date — end of lookback window
        tomorrow_load: str — 'light', 'moderate', or 'heavy'
        daily_loads: dict[date, str] — pre-computed load per day
        completion_dates: set[date] — dates where behavior occurred
        behavior_name: str — display name

    Returns:
        dict with behavior, probability, note — or None
    """
    try:
        total_matching_days = 0
        completed_matching_days = 0
        total_all_days = 0
        completed_all_days = 0

        current = lookback_start
        while current <= today:
            completed = current in completion_dates
            total_all_days += 1
            if completed:
                completed_all_days += 1

            # Classify that day's load (default to 'light' if no events)
            day_load = daily_loads.get(current, 'light')
            if day_load == tomorrow_load:
                total_matching_days += 1
                if completed:
                    completed_matching_days += 1

            current += timedelta(days=1)

        # Need minimum data for meaningful prediction
        if total_all_days < 7:
            return None

        # Use load-specific rate if we have enough data, else overall
        if total_matching_days >= 5:
            probability = int(
                (completed_matching_days / total_matching_days) * 100
            )
            note = (
                f"Based on {total_matching_days} similar "
                f"{tomorrow_load}-load days"
            )
        else:
            probability = int((completed_all_days / total_all_days) * 100)
            note = f"Based on {total_all_days}-day history"

        return {
            'behavior': behavior_name,
            'probability': probability,
            'note': note,
        }

    except Exception as e:
        logger.debug("Forecast for %s failed: %s", behavior_name, e)
        return None


# ═══════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════

def _count_to_load(count):
    """Convert event count to load classification."""
    if count >= 5:
        return 'heavy'
    elif count >= 3:
        return 'moderate'
    return 'light'


def _load_description(load):
    """Human-readable load description."""
    return {
        'heavy': "Heavy (5+ events scheduled)",
        'moderate': "Moderate (3-4 events)",
        'light': "Light schedule",
    }.get(load, "")
