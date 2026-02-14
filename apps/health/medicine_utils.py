"""
Medicine adherence calculation utilities.

IMPORTANT: Adherence must be calculated against EXPECTED doses from schedules,
not just the ratio of taken/missed logs. If a user has 20 expected doses but
only logged 2 as 'taken' and never interacted with the other 18, the old
calculation (2 / (2+0) = 100%) was wrong. Correct: 2 / 20 = 10%.

This module provides a single source of truth for adherence calculations
used across dashboard_ai, dashboard cache, personal_assistant, and trend_tracking.
"""

from datetime import date, timedelta


def calculate_medicine_adherence(user, start_date, end_date):
    """
    Calculate medicine adherence rate for a date range.

    Returns dict with:
        - expected_doses: total scheduled doses in the period
        - taken_doses: doses logged as taken or late
        - missed_doses: doses explicitly marked missed
        - unlogged_doses: expected but no log entry exists
        - adherence_rate: percentage (0-100) or None if no expected doses

    Calculation: taken / expected * 100
    This is the CORRECT formula — it counts unlogged doses as not taken.
    """
    from apps.health.models import Medicine, MedicineLog, MedicineSchedule

    active_medicines = Medicine.objects.filter(
        user=user,
        medicine_status=Medicine.STATUS_ACTIVE,
    ).prefetch_related("schedules")

    # Count expected doses by iterating each day and checking schedules
    expected_doses = 0
    day = start_date
    schedule_day_map = []  # List of (medicine_id, schedule_id, date) tuples

    while day <= end_date:
        day_of_week = day.weekday()  # 0=Mon, 6=Sun
        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(is_active=True):
                if schedule.applies_to_day(day_of_week):
                    expected_doses += 1
                    schedule_day_map.append((medicine.id, schedule.id, day))
        day += timedelta(days=1)

    if expected_doses == 0:
        return {
            "expected_doses": 0,
            "taken_doses": 0,
            "missed_doses": 0,
            "unlogged_doses": 0,
            "adherence_rate": None,
        }

    # Count actual logs in the period
    logs = MedicineLog.objects.filter(
        user=user,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
    )
    taken_count = logs.filter(log_status__in=["taken", "late"]).count()
    missed_count = logs.filter(log_status="missed").count()
    # Skipped doses are intentional — don't count against or for adherence
    skipped_count = logs.filter(log_status="skipped").count()

    # Unlogged = expected minus all interactions (taken + missed + skipped)
    logged_count = taken_count + missed_count + skipped_count
    unlogged_count = max(0, expected_doses - logged_count)

    # Adherence = taken / (expected - skipped)
    # Skipped doses are intentional non-takes, so we exclude them from the denominator
    effective_expected = expected_doses - skipped_count
    if effective_expected > 0:
        adherence_rate = round((taken_count / effective_expected) * 100)
    else:
        adherence_rate = None

    return {
        "expected_doses": expected_doses,
        "taken_doses": taken_count,
        "missed_doses": missed_count,
        "unlogged_doses": unlogged_count,
        "adherence_rate": adherence_rate,
    }


def calculate_medicine_adherence_rate(user, days=7):
    """
    Convenience wrapper: returns just the adherence rate (int or None)
    for the past N days.
    """
    from django.utils import timezone
    from apps.core.utils import get_user_today

    today = get_user_today(user)
    start = today - timedelta(days=days)
    result = calculate_medicine_adherence(user, start, today)
    return result["adherence_rate"]
