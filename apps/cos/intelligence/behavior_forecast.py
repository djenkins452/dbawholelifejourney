"""
COS-CX6: Behavioral Forecast Extension
=======================================

Predicts probability of completing key behaviors based on historical
patterns, schedule load, and pressure level.

"Workout completion probability tomorrow: 28%. Heavy meeting load detected."

This extends the Drift Engine concept with historical behavioral
correlation — on heavy schedule days, which behaviors get dropped?

Performance target: < 8ms (bounded historical queries).
Token budget: ~100 tokens max.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

MAX_FORECAST_ITEMS = 3
LOOKBACK_WEEKS = 8  # 8-week history for pattern detection


def compute_behavior_forecast(user, now, cos_context=None):
    """
    Predict probability of completing key behaviors tomorrow.

    Uses historical completion rates segmented by schedule load
    (light day vs. heavy day) and current conditions.

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

        # Step 1: Determine tomorrow's schedule load
        tomorrow_load = _get_schedule_load(user, tomorrow, now.tzinfo)

        # Step 2: Compute historical completion by load level
        forecasts = []

        # Workout forecast
        workout_forecast = _forecast_behavior(
            user, today, tomorrow_load,
            behavior_name="Workout",
            query_fn=_workout_completion_by_day,
        )
        if workout_forecast:
            forecasts.append(workout_forecast)

        # Reading plan / quiet time forecast
        reading_forecast = _forecast_behavior(
            user, today, tomorrow_load,
            behavior_name="Bible Reading",
            query_fn=_reading_completion_by_day,
        )
        if reading_forecast:
            forecasts.append(reading_forecast)

        # Journal forecast
        journal_forecast = _forecast_behavior(
            user, today, tomorrow_load,
            behavior_name="Journal Entry",
            query_fn=_journal_completion_by_day,
        )
        if journal_forecast:
            forecasts.append(journal_forecast)

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


def _get_schedule_load(user, target_date, tzinfo):
    """
    Classify schedule load for a given date.
    Returns: 'light' (0-2 events), 'moderate' (3-4), 'heavy' (5+)
    """
    try:
        from apps.calendar_engine.models import CalendarEvent

        count = CalendarEvent.objects.filter(
            user=user,
            start_dt__date=target_date,
            deleted_at__isnull=True,
        ).exclude(status='canceled').count()

        if count >= 5:
            return 'heavy'
        elif count >= 3:
            return 'moderate'
        return 'light'
    except Exception:
        return 'light'


def _forecast_behavior(user, today, tomorrow_load, behavior_name, query_fn):
    """
    Generic behavior forecaster.
    Computes historical completion rate segmented by load level.

    Args:
        query_fn: function(user, date) -> bool (did behavior happen that day)

    Returns:
        dict with behavior, probability, note — or None
    """
    try:
        lookback_start = today - timedelta(weeks=LOOKBACK_WEEKS)

        # Get daily completion data with load classification
        total_matching_days = 0
        completed_matching_days = 0
        total_all_days = 0
        completed_all_days = 0

        # Sample days in the lookback window (every day)
        current = lookback_start
        while current <= today:
            completed = query_fn(user, current)
            if completed is None:
                # Query couldn't determine — skip
                current += timedelta(days=1)
                continue

            total_all_days += 1
            if completed:
                completed_all_days += 1

            # Classify that day's load
            day_load = _get_schedule_load_cached(user, current)
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
            probability = int((completed_matching_days / total_matching_days) * 100)
            note = f"Based on {total_matching_days} similar {tomorrow_load}-load days"
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


# Cache for schedule load to avoid repeated queries during forecast
_load_cache = {}


def _get_schedule_load_cached(user, date):
    """Cached version of schedule load — avoids N+1 during forecast loop."""
    cache_key = f"{user.id}:{date}"
    if cache_key not in _load_cache:
        try:
            from apps.calendar_engine.models import CalendarEvent
            count = CalendarEvent.objects.filter(
                user=user,
                start_dt__date=date,
                deleted_at__isnull=True,
            ).exclude(status='canceled').count()
            _load_cache[cache_key] = 'heavy' if count >= 5 else (
                'moderate' if count >= 3 else 'light'
            )
        except Exception:
            _load_cache[cache_key] = 'light'

        # Prevent unbounded cache growth
        if len(_load_cache) > 200:
            _load_cache.clear()

    return _load_cache[cache_key]


def _workout_completion_by_day(user, date):
    """Did user complete a workout on this date?"""
    try:
        from apps.health.models import WorkoutSession
        return WorkoutSession.objects.filter(user=user, date=date).exists()
    except Exception:
        return None


def _reading_completion_by_day(user, date):
    """Did user complete a reading plan day on this date?"""
    try:
        from apps.faith.models import UserReadingProgress
        return UserReadingProgress.objects.filter(
            user_plan__user=user,
            completed_at__date=date,
        ).exists()
    except Exception:
        return None


def _journal_completion_by_day(user, date):
    """Did user write a journal entry on this date?"""
    try:
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.filter(
            user=user,
            created_at__date=date,
        ).exists()
    except Exception:
        return None


def _load_description(load):
    """Human-readable load description."""
    return {
        'heavy': "Heavy (5+ events scheduled)",
        'moderate': "Moderate (3-4 events)",
        'light': "Light schedule",
    }.get(load, "")
