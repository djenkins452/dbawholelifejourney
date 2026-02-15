"""
SAE — State Builders.

Modular functions that read actual database records and produce
accurate structured state for each domain module.

Safety Requirements:
- State must always reflect actual database values
- State must never invent or infer unsupported values
- Each builder produces a dict that becomes one module key in state_data
"""

import logging
from datetime import timedelta

from apps.core.time.system_clock import get_current_time

logger = logging.getLogger(__name__)


def build_health_state(user):
    """
    Build health state from actual database records.

    Returns:
        dict with weight, body fat, sleep, steps, vitals summaries.
    """
    from apps.health.models import (
        BloodPressureEntry,
        BodyCompositionEntry,
        SleepEntry,
        StepsEntry,
        WeightEntry,
    )

    now = get_current_time()
    state = {}

    # ── Weight ──────────────────────────────────────────────
    latest_weight = (
        WeightEntry.objects.filter(user=user)
        .order_by("-recorded_at")
        .values_list("value", "unit", "recorded_at")
        .first()
    )
    if latest_weight:
        val, unit, recorded_at = latest_weight
        state["weight_current"] = float(val)
        state["weight_unit"] = unit
        state["last_weight_entry"] = recorded_at.isoformat()

        # Trend: compare latest to 30 days ago
        cutoff_30d = now - timedelta(days=30)
        older_weight = (
            WeightEntry.objects.filter(user=user, recorded_at__lte=cutoff_30d)
            .order_by("-recorded_at")
            .values_list("value", flat=True)
            .first()
        )
        if older_weight is not None:
            diff = float(val) - float(older_weight)
            if abs(diff) < 0.5:
                state["weight_trend"] = "stable"
            elif diff > 0:
                state["weight_trend"] = "increasing"
            else:
                state["weight_trend"] = "decreasing"
        else:
            state["weight_trend"] = "insufficient_data"

        # Weight entry count (last 90 days)
        cutoff_90d = now - timedelta(days=90)
        state["weight_entries_90d"] = WeightEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_90d
        ).count()

    # ── Body Composition ─────────────────────────────────────
    latest_bf = (
        BodyCompositionEntry.objects.filter(
            user=user, metric_name="body_fat_pct"
        )
        .order_by("-measurement_date")
        .values_list("value", "measurement_date")
        .first()
    )
    if latest_bf:
        state["body_fat_current"] = float(latest_bf[0])
        state["last_body_fat_entry"] = latest_bf[1].isoformat()

    latest_lm = (
        BodyCompositionEntry.objects.filter(
            user=user, metric_name="lean_mass"
        )
        .order_by("-measurement_date")
        .values_list("value", "measurement_date")
        .first()
    )
    if latest_lm:
        state["lean_mass_current"] = float(latest_lm[0])
        state["last_lean_mass_entry"] = latest_lm[1].isoformat()

    # ── Sleep (last 7 days) ───────────────────────────────────
    cutoff_7d = now - timedelta(days=7)
    recent_sleep = SleepEntry.objects.filter(
        user=user, sleep_date__gte=cutoff_7d.date()
    )
    sleep_count = recent_sleep.count()
    if sleep_count > 0:
        from django.db.models import Avg

        avg_duration = recent_sleep.aggregate(
            avg=Avg("total_duration_minutes")
        )["avg"]
        state["sleep_avg_duration_7d"] = round(float(avg_duration), 1) if avg_duration else None
        state["sleep_entries_7d"] = sleep_count

        last_sleep = (
            SleepEntry.objects.filter(user=user)
            .order_by("-sleep_date")
            .values_list("sleep_date", flat=True)
            .first()
        )
        if last_sleep:
            state["last_sleep_entry"] = last_sleep.isoformat()

    # ── Steps (last 7 days) ───────────────────────────────────
    recent_steps = StepsEntry.objects.filter(
        user=user, logged_date__gte=cutoff_7d.date()
    )
    steps_count = recent_steps.count()
    if steps_count > 0:
        from django.db.models import Avg

        avg_steps = recent_steps.aggregate(avg=Avg("count"))["avg"]
        state["steps_avg_7d"] = round(float(avg_steps)) if avg_steps else None
        state["steps_entries_7d"] = steps_count

    # ── Blood Pressure (latest) ──────────────────────────────
    latest_bp = (
        BloodPressureEntry.objects.filter(user=user)
        .order_by("-recorded_at")
        .values_list("systolic", "diastolic", "recorded_at")
        .first()
    )
    if latest_bp:
        state["bp_systolic"] = latest_bp[0]
        state["bp_diastolic"] = latest_bp[1]
        state["last_bp_entry"] = latest_bp[2].isoformat()

    return state


def build_goal_state(user):
    """
    Build goal state from actual database records.

    Returns:
        dict with active goals, completion rate, next deadline.
    """
    from apps.purpose.models import LifeGoal

    now = get_current_time()
    state = {}

    active_goals = LifeGoal.objects.filter(user=user, status="active")
    state["active_goal_count"] = active_goals.count()

    if state["active_goal_count"] == 0:
        return state

    # Completion rate across all active goals (milestone-based)
    total_milestones = 0
    completed_milestones = 0
    next_deadline = None

    for goal in active_goals:
        milestones = goal.milestones.all()
        total = milestones.count()
        completed = milestones.filter(completed=True).count()
        total_milestones += total
        completed_milestones += completed

        # Track next deadline
        if goal.target_date:
            if next_deadline is None or goal.target_date < next_deadline:
                next_deadline = goal.target_date

    if total_milestones > 0:
        state["completion_rate"] = round(
            completed_milestones / total_milestones, 2
        )
        state["total_milestones"] = total_milestones
        state["completed_milestones"] = completed_milestones
    else:
        state["completion_rate"] = 0.0

    if next_deadline:
        state["next_deadline"] = next_deadline.isoformat()
        state["days_to_next_deadline"] = (next_deadline - now.date()).days

    # Overdue goals
    overdue = active_goals.filter(target_date__lt=now.date()).count()
    state["overdue_goal_count"] = overdue

    return state


def build_habit_state(user):
    """
    Build habit state from actual database records.

    Returns:
        dict with active habits, streaks, last activity.
    """
    from apps.purpose.models import HabitGoal

    state = {}

    active_habits = HabitGoal.objects.filter(user=user, status="active")
    state["active_habit_count"] = active_habits.count()

    if state["active_habit_count"] == 0:
        return state

    longest_streak = 0
    total_completion_rate = 0.0
    last_activity = None

    for habit in active_habits:
        # Use the model's built-in properties
        streak = habit.current_streak
        if streak > longest_streak:
            longest_streak = streak

        total_completion_rate += habit.completion_rate

        # Find last activity
        last_entry = (
            habit.habit_entries.filter(completed=True)
            .order_by("-date")
            .values_list("date", flat=True)
            .first()
        )
        if last_entry:
            if last_activity is None or last_entry > last_activity:
                last_activity = last_entry

    state["longest_streak"] = longest_streak
    state["avg_completion_rate"] = round(
        total_completion_rate / state["active_habit_count"], 2
    )

    if last_activity:
        state["last_activity"] = last_activity.isoformat()

    return state


def build_faith_state(user):
    """
    Build faith state from actual database records.

    Returns:
        dict with reading plans, scripture streak, prayer requests.
    """
    from apps.faith.models import PrayerRequest, UserReadingPlan, UserReadingProgress

    now = get_current_time()
    state = {}

    # Active reading plans
    active_plans = UserReadingPlan.objects.filter(
        user=user, plan_status="active"
    )
    state["active_reading_plans"] = active_plans.count()

    # Last scripture reading
    last_reading = (
        UserReadingProgress.objects.filter(
            user_plan__user=user, is_completed=True
        )
        .order_by("-completed_at")
        .values_list("completed_at", flat=True)
        .first()
    )
    if last_reading:
        state["last_scripture_read"] = last_reading.isoformat()
        state["days_since_reading"] = (now - last_reading).days

    # Reading streak (consecutive days with completions)
    streak = _calculate_reading_streak(user, now)
    state["reading_streak"] = streak

    # Prayer requests
    state["unanswered_prayers"] = PrayerRequest.objects.filter(
        user=user, is_answered=False
    ).count()

    return state


def _calculate_reading_streak(user, now):
    """Calculate consecutive days of scripture reading ending at today/yesterday."""
    from apps.faith.models import UserReadingProgress

    # Get distinct completion dates in reverse order
    completion_dates = list(
        UserReadingProgress.objects.filter(
            user_plan__user=user, is_completed=True, completed_at__isnull=False
        )
        .values_list("completed_at__date", flat=True)
        .distinct()
        .order_by("-completed_at__date")[:60]  # Look back max 60 days
    )

    if not completion_dates:
        return 0

    today = now.date()
    streak = 0

    # Start from today or yesterday
    check_date = today
    if completion_dates[0] < today:
        # Allow streak to include yesterday
        check_date = completion_dates[0]
        if (today - check_date).days > 1:
            return 0  # Gap too large

    for comp_date in completion_dates:
        if comp_date == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        elif comp_date < check_date:
            break  # Gap found

    return streak


def build_journal_state(user):
    """
    Build journal state from actual database records.

    Returns:
        dict with last entry, frequency, mood distribution.
    """
    from apps.journal.models import JournalEntry

    now = get_current_time()
    state = {}

    # Last journal entry
    last_entry = (
        JournalEntry.objects.filter(user=user)
        .order_by("-entry_date")
        .values_list("entry_date", "mood", "word_count")
        .first()
    )
    if last_entry:
        state["last_entry"] = last_entry[0].isoformat()
        state["last_mood"] = last_entry[1] or ""
        state["days_since_entry"] = (now.date() - last_entry[0]).days

    # Entry frequency (entries per week over last 30 days)
    cutoff_30d = now - timedelta(days=30)
    recent_count = JournalEntry.objects.filter(
        user=user, entry_date__gte=cutoff_30d.date()
    ).count()
    state["entry_frequency"] = round(recent_count / 4.3, 1)  # per week
    state["entries_30d"] = recent_count

    # Mood distribution (last 30 days)
    if recent_count > 0:
        from django.db.models import Count

        mood_counts = dict(
            JournalEntry.objects.filter(
                user=user, entry_date__gte=cutoff_30d.date()
            )
            .exclude(mood="")
            .values_list("mood")
            .annotate(count=Count("id"))
            .values_list("mood", "count")
        )
        if mood_counts:
            state["mood_distribution"] = mood_counts

    return state


# ── Builder Registry ─────────────────────────────────────────────

# Maps module names to their builder functions.
# New modules can be registered by adding to this dict.
MODULE_BUILDERS = {
    "health": build_health_state,
    "goals": build_goal_state,
    "purpose": build_goal_state,  # alias
    "habits": build_habit_state,
    "faith": build_faith_state,
    "journal": build_journal_state,
}


def get_builder(module):
    """Get the state builder function for a module."""
    return MODULE_BUILDERS.get(module)


def get_all_builders():
    """Get all unique builder functions (no aliases)."""
    seen = set()
    builders = {}
    for module, builder in MODULE_BUILDERS.items():
        if id(builder) not in seen:
            seen.add(id(builder))
            builders[module] = builder
    return builders
