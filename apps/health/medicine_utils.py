"""
Medicine adherence calculation utilities.

IMPORTANT: Adherence must be calculated against EXPECTED doses from schedules,
not just the ratio of taken/missed logs. If a user has 20 expected doses but
only logged 2 as 'taken' and never interacted with the other 18, the old
calculation (2 / (2+0) = 100%) was wrong. Correct: 2 / 20 = 10%.

Fairness rule: today's future doses (scheduled_time > now) are excluded
from expected count. You can't miss a dose that isn't due yet.

This module provides a single source of truth for adherence calculations
used across dashboard_ai, dashboard cache, personal_assistant, and trend_tracking.
"""

from datetime import date, timedelta


def _enumerate_expected_doses(active_medicines, start_date, end_date, user_today, current_time):
    """Single source of truth for the expected-dose algorithm.

    Walks every day in [start_date, end_date] and yields one entry per
    active schedule that applies to that day. Today's not-yet-due doses
    (scheduled_time > now) are excluded — you can't miss a dose that
    isn't due yet (fairness rule, see module docstring).

    This is the ONE expected-dose enumeration shared by every adherence
    calculation in this module (range, single-medicine, and per-day
    chart). Do NOT re-implement the schedule walk elsewhere — call this.

    Args:
        active_medicines: iterable of Intake instances (active only).
        start_date / end_date: inclusive date range.
        user_today: the user's local "today" (date).
        current_time: the user's local current time (datetime.time).

    Returns:
        list of (medicine_id, schedule_id, day) tuples. len() of the
        returned list is the expected-dose count for the range.
    """
    expected = []
    day = start_date
    while day <= end_date:
        day_of_week = day.weekday()  # 0=Mon, 6=Sun
        is_today = (day == user_today)
        for medicine in active_medicines:
            for schedule in medicine.schedules.filter(is_active=True):
                if schedule.applies_to_day(day_of_week):
                    if is_today and schedule.scheduled_time and schedule.scheduled_time > current_time:
                        # Future dose today — not due yet, skip
                        continue
                    expected.append((medicine.id, schedule.id, day))
        day += timedelta(days=1)
    return expected


def get_expected_dose_entries(
    user, start_date, end_date, *, intake_type=None, active_medicines=None
):
    """Public single-source expected-dose enumeration for callers OUTSIDE this module.

    This is the ONE expected-dose enumeration shared across WLJ (Medication
    Intelligence Canon §5 — "expected dose has exactly one author"). Adherence
    and compliance engines MUST call this instead of re-walking schedules, so
    every engine agrees on the denominator and on the future-dose-today fairness
    rule (a dose scheduled later today is not yet due and is not "expected").

    Args:
        user: Django User.
        start_date / end_date: inclusive date range.
        intake_type: optional 'medication' | 'supplement' | None (all).
        active_medicines: optional pre-fetched iterable of ACTIVE Intake
            instances (avoids a duplicate query when the caller already holds
            them). When omitted, active intakes are fetched here.

    Returns:
        list of (medicine_id, schedule_id, day) tuples — len() is the
        expected-dose count for the range.
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import Intake

    if active_medicines is None:
        qs = Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE)
        if intake_type:
            qs = qs.filter(intake_type=intake_type)
        active_medicines = qs.prefetch_related("schedules")

    user_today = get_user_today(user)
    current_time = get_user_now(user).time()

    return _enumerate_expected_doses(
        active_medicines, start_date, end_date, user_today, current_time
    )


def calculate_medicine_adherence(user, start_date, end_date, intake_type=None):
    """
    Calculate medicine adherence rate for a date range.

    Args:
        user: Django User instance
        start_date: date — inclusive start
        end_date: date — inclusive end
        intake_type: optional — 'medication', 'supplement', or None for all

    Returns dict with:
        - expected_doses: total scheduled doses in the period
        - taken_doses: doses logged as taken or late
        - missed_doses: doses explicitly marked missed
        - unlogged_doses: expected but no log entry exists
        - adherence_rate: percentage (0-100) or None if no expected doses

    Calculation: taken / expected * 100
    This is the CORRECT formula — it counts unlogged doses as not taken.
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import Intake, IntakeLog, IntakeSchedule

    qs = Intake.objects.filter(
        user=user,
        intake_status=Intake.STATUS_ACTIVE,
    )
    if intake_type:
        qs = qs.filter(intake_type=intake_type)
    active_medicines = qs.prefetch_related("schedules")

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()

    # Count expected doses via the single canonical enumeration.
    schedule_day_map = _enumerate_expected_doses(
        active_medicines, start_date, end_date, user_today, current_time
    )
    expected_doses = len(schedule_day_map)

    if expected_doses == 0:
        return {
            "expected_doses": 0,
            "taken_doses": 0,
            "missed_doses": 0,
            "unlogged_doses": 0,
            "adherence_rate": None,
        }

    # Count actual logs in the period
    # Filter to active medicines only so logs from discontinued medicines
    # don't inflate the taken count beyond expected.
    logs = IntakeLog.objects.filter(
        user=user,
        intake__in=active_medicines,
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
    # Skipped doses are intentional non-takes, so we exclude them from the denominator.
    # Cap at 100: an adherence rate above 100% is nonsensical and happens
    # when log entries exceed the schedule-derived expected count (e.g.,
    # "as-needed" logs or mid-window schedule changes). Phase 6 audit
    # fix, 2026-04-08.
    effective_expected = expected_doses - skipped_count
    if effective_expected > 0:
        adherence_rate = min(100, round((taken_count / effective_expected) * 100))
    else:
        adherence_rate = None

    return {
        "expected_doses": expected_doses,
        "taken_doses": taken_count,
        "missed_doses": missed_count,
        "skipped_doses": skipped_count,
        "unlogged_doses": unlogged_count,
        "adherence_rate": adherence_rate,
    }


def calculate_single_medicine_adherence(user, medicine, start_date, end_date):
    """
    Calculate adherence for a SINGLE medicine over a date range.

    Uses schedule-based expected doses (same approach as the overall calc)
    so unlogged doses count as missed — not invisible.

    Returns dict with:
        - expected_doses: total scheduled doses in the period
        - taken_doses: doses logged as taken or late
        - adherence_rate: percentage (0-100) or None if no expected doses
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import IntakeLog

    user_today = get_user_today(user)
    user_now = get_user_now(user)
    current_time = user_now.time()

    # Count expected doses via the single canonical enumeration (one medicine).
    expected_doses = len(_enumerate_expected_doses(
        [medicine], start_date, end_date, user_today, current_time
    ))

    if expected_doses == 0:
        return {
            "expected_doses": 0,
            "taken_doses": 0,
            "adherence_rate": None,
        }

    # Count actual taken/late logs
    logs = IntakeLog.objects.filter(
        user=user,
        intake=medicine,
        scheduled_date__gte=start_date,
        scheduled_date__lte=end_date,
    )
    taken_count = logs.filter(log_status__in=["taken", "late"]).count()
    skipped_count = logs.filter(log_status="skipped").count()

    effective_expected = expected_doses - skipped_count
    if effective_expected > 0:
        adherence_rate = min(100, round((taken_count / effective_expected) * 100))
    else:
        adherence_rate = None

    return {
        "expected_doses": expected_doses,
        "taken_doses": taken_count,
        "adherence_rate": adherence_rate,
    }


def calculate_medicine_adherence_rate(user, days=7, intake_type=None):
    """
    Convenience wrapper: returns just the adherence rate (int or None)
    for the past N days.

    Args:
        intake_type: optional — 'medication', 'supplement', or None for all
    """
    from apps.core.utils import get_user_today

    today = get_user_today(user)
    start = today - timedelta(days=days)
    result = calculate_medicine_adherence(user, start, today, intake_type=intake_type)
    return result["adherence_rate"]


def calculate_daily_medicine_adherence(user, start_date, end_date, intake_type=None):
    """
    Per-day adherence breakdown for charts.

    Each day uses the EXACT same expected-dose enumeration
    (``_enumerate_expected_doses``) and the same
    ``taken / (expected - skipped)`` formula as
    ``calculate_medicine_adherence``. Because a single day computed here is
    identical to ``calculate_medicine_adherence(user, day, day)``, the daily
    chart can never disagree with the headline for the same day.

    This replaces the old logs-only chart calculation in the adherence view,
    which counted only LOGGED doses as the denominator and defaulted to 100%
    on days with no logs — silently disagreeing with the schedule-based
    headline (D2 drift).

    Args:
        user: Django User instance.
        start_date / end_date: inclusive date range.
        intake_type: optional — 'medication', 'supplement', or None for all.

    Returns:
        list (ordered start_date..end_date) of dicts, one per day:
            - date: ISO date string
            - expected_doses: scheduled doses that day (today's not-yet-due
              doses excluded)
            - taken_doses: doses logged taken or late
            - skipped_doses: doses logged skipped (excluded from denominator)
            - adherence_rate: taken / (expected - skipped) * 100, capped at
              100, or None when there is nothing to measure (no expected
              doses, or every expected dose was skipped). None means
              "no data" — explicitly NOT 100%.
    """
    from apps.core.utils import get_user_now, get_user_today
    from apps.health.models import Intake, IntakeLog

    qs = Intake.objects.filter(
        user=user,
        intake_status=Intake.STATUS_ACTIVE,
    )
    if intake_type:
        qs = qs.filter(intake_type=intake_type)
    active_medicines = list(qs.prefetch_related("schedules"))

    user_today = get_user_today(user)
    current_time = get_user_now(user).time()

    # Bucket expected doses per day from the canonical enumeration.
    expected_by_day = {}
    for _med_id, _sched_id, day in _enumerate_expected_doses(
        active_medicines, start_date, end_date, user_today, current_time
    ):
        expected_by_day[day] = expected_by_day.get(day, 0) + 1

    # Bucket logs per day in a single query. Mirrors the headline's log
    # handling: taken/late count toward adherence; skipped leaves the
    # denominator; everything else (missed, unlogged) counts as not taken.
    taken_by_day = {}
    skipped_by_day = {}
    if active_medicines:
        log_rows = IntakeLog.objects.filter(
            user=user,
            intake__in=active_medicines,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        ).values_list("scheduled_date", "log_status")
        for sched_date, status in log_rows:
            if status in ("taken", "late"):
                taken_by_day[sched_date] = taken_by_day.get(sched_date, 0) + 1
            elif status == "skipped":
                skipped_by_day[sched_date] = skipped_by_day.get(sched_date, 0) + 1

    daily = []
    day = start_date
    while day <= end_date:
        expected = expected_by_day.get(day, 0)
        taken = taken_by_day.get(day, 0)
        skipped = skipped_by_day.get(day, 0)
        effective_expected = expected - skipped
        if effective_expected > 0:
            rate = min(100, round((taken / effective_expected) * 100))
        else:
            rate = None  # No data — NOT 100%
        daily.append({
            "date": day.isoformat(),
            "expected_doses": expected,
            "taken_doses": taken,
            "skipped_doses": skipped,
            "adherence_rate": rate,
        })
        day += timedelta(days=1)
    return daily
