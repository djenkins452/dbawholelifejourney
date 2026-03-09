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

    latest_fm = (
        BodyCompositionEntry.objects.filter(
            user=user, metric_name="fat_mass"
        )
        .order_by("-measurement_date")
        .values_list("value", "measurement_date")
        .first()
    )
    if latest_fm:
        state["fat_mass_current"] = float(latest_fm[0])
        state["last_fat_mass_entry"] = latest_fm[1].isoformat()

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

    # ── Heart Rate (7-day avg) ────────────────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import HeartRateEntry

        hr_avg = HeartRateEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("bpm"))["avg"]
        if hr_avg:
            state["heart_rate_avg_7d"] = round(float(hr_avg))
    except Exception:
        pass

    # ── Glucose (7-day avg) ───────────────────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import GlucoseEntry

        glucose_avg = GlucoseEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("value"))["avg"]
        if glucose_avg:
            state["glucose_avg_7d"] = round(float(glucose_avg))
    except Exception:
        pass

    # ── Blood Oxygen (7-day avg) ──────────────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import BloodOxygenEntry

        spo2_avg = BloodOxygenEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("spo2"))["avg"]
        if spo2_avg:
            state["blood_oxygen_avg_7d"] = round(float(spo2_avg), 1)
    except Exception:
        pass

    # ── Heart Rate Events (7-day count) ───────────────────────
    try:
        from apps.health.models import HeartRateEventEntry

        hr_events = HeartRateEventEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).count()
        if hr_events > 0:
            state["heart_rate_events_7d"] = hr_events
    except Exception:
        pass

    # ── Weight Goal (from HealthProfile) ──────────────────────
    try:
        from apps.health.models import HealthProfile

        hp = HealthProfile.objects.filter(user=user).first()
        if hp and hp.has_weight_goal:
            state["weight_goal"] = float(hp.weight_goal)
            state["weight_goal_unit"] = hp.weight_goal_unit
            if hp.weight_goal_target_date:
                state["weight_goal_target_date"] = str(hp.weight_goal_target_date)
            progress = hp.get_weight_progress()
            if progress and progress.get("remaining") is not None:
                state["weight_goal_remaining"] = progress["remaining"]
                state["weight_goal_on_track"] = progress.get("on_track")
    except Exception:
        pass

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
    # habit.completion_rate returns 0-100; normalize to 0-1 for consumers
    state["avg_completion_rate"] = round(
        (total_completion_rate / state["active_habit_count"]) / 100, 2
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

    state["answered_prayers"] = PrayerRequest.objects.filter(
        user=user, is_answered=True
    ).count()

    # Recent prayer titles (top 5 active)
    state["recent_prayer_titles"] = list(
        PrayerRequest.objects.filter(user=user, is_answered=False)
        .order_by("-created_at")
        .values_list("title", flat=True)[:5]
    )

    # Urgent prayers
    state["urgent_prayers"] = PrayerRequest.objects.filter(
        user=user, is_answered=False, priority="urgent"
    ).count()

    # Bible reading plan name
    active_plan = active_plans.first()
    if active_plan and hasattr(active_plan, "plan"):
        state["bible_plan_name"] = str(active_plan.plan)

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


# ── Nutrition State ──────────────────────────────────────────────


def build_nutrition_state(user):
    """
    Build nutrition state from actual database records.

    Returns:
        dict with daily intake, targets, compliance, rolling averages.
    """
    from django.db.models import Avg, Sum

    from apps.health.models import DailyNutritionSummary, FoodEntry, NutritionGoals

    now = get_current_time()
    today = now.date()
    state = {}

    # ── Today's intake (from FoodEntry for current day) ──────────
    today_entries = FoodEntry.objects.filter(
        user=user, logged_date=today, status="active"
    )
    today_count = today_entries.count()
    if today_count > 0:
        totals = today_entries.aggregate(
            calories=Sum("total_calories"),
            protein=Sum("total_protein_g"),
            carbs=Sum("total_carbohydrates_g"),
            fat=Sum("total_fat_g"),
            fiber=Sum("total_fiber_g"),
        )
        state["daily_calories"] = round(float(totals["calories"] or 0), 1)
        state["daily_protein_g"] = round(float(totals["protein"] or 0), 1)
        state["daily_carbs_g"] = round(float(totals["carbs"] or 0), 1)
        state["daily_fat_g"] = round(float(totals["fat"] or 0), 1)
        state["daily_fiber_g"] = round(float(totals["fiber"] or 0), 1)
    state["food_entries_today"] = today_count

    # ── Active nutrition goals ───────────────────────────────────
    active_goals = (
        NutritionGoals.objects.filter(
            user=user,
            effective_from__lte=today,
        )
        .filter(
            # effective_until is null (still active) or in the future
            **{"effective_until__gte": today}
        )
        | NutritionGoals.objects.filter(
            user=user,
            effective_from__lte=today,
            effective_until__isnull=True,
        )
    )
    goal = active_goals.order_by("-effective_from").first()
    if goal:
        if goal.daily_calorie_target:
            state["calorie_target"] = goal.daily_calorie_target
        if goal.daily_protein_target_g:
            state["protein_target"] = float(goal.daily_protein_target_g)
        if goal.daily_carb_target_g:
            state["carb_target"] = float(goal.daily_carb_target_g)
        if goal.daily_fat_target_g:
            state["fat_target"] = float(goal.daily_fat_target_g)

    # ── Compliance (today vs targets) ────────────────────────────
    if today_count > 0 and goal:
        if goal.daily_calorie_target and goal.daily_calorie_target > 0:
            state["calorie_compliance_pct"] = round(
                state["daily_calories"] / goal.daily_calorie_target * 100, 1
            )
        if goal.daily_protein_target_g and float(goal.daily_protein_target_g) > 0:
            state["protein_compliance_pct"] = round(
                state["daily_protein_g"] / float(goal.daily_protein_target_g) * 100, 1
            )
        if goal.daily_carb_target_g and float(goal.daily_carb_target_g) > 0:
            state["carb_compliance_pct"] = round(
                state["daily_carbs_g"] / float(goal.daily_carb_target_g) * 100, 1
            )

        # Macro compliance score (average of available compliance percentages)
        compliance_values = []
        for key in ("calorie_compliance_pct", "protein_compliance_pct", "carb_compliance_pct"):
            val = state.get(key)
            if val is not None:
                # Score: 100 = perfect, penalize over/under equally
                compliance_values.append(max(0, 100 - abs(100 - val)))
        if compliance_values:
            state["macro_compliance_score"] = round(
                sum(compliance_values) / len(compliance_values), 1
            )

    # ── Rolling 7-day averages (from DailyNutritionSummary) ──────
    cutoff_7d = today - timedelta(days=7)
    summaries_7d = DailyNutritionSummary.objects.filter(
        user=user, summary_date__gte=cutoff_7d, summary_date__lt=today
    )
    summary_count = summaries_7d.count()
    if summary_count > 0:
        avgs = summaries_7d.aggregate(
            avg_cal=Avg("total_calories"),
            avg_protein=Avg("total_protein_g"),
        )
        state["rolling_7d_calories_avg"] = round(float(avgs["avg_cal"] or 0), 1)
        state["rolling_7d_protein_avg"] = round(float(avgs["avg_protein"] or 0), 1)

    # ── Last food entry ──────────────────────────────────────────
    last_entry = (
        FoodEntry.objects.filter(user=user, status="active")
        .order_by("-logged_date", "-logged_time")
        .values_list("logged_date", flat=True)
        .first()
    )
    if last_entry:
        state["last_food_entry"] = last_entry.isoformat()

    # ── 7-day food entry count ───────────────────────────────────
    state["food_entries_7d"] = FoodEntry.objects.filter(
        user=user, logged_date__gte=cutoff_7d, status="active"
    ).count()

    return state


# ── Fasting State ───────────────────────────────────────────────


def build_fasting_state(user):
    """
    Build fasting state from actual database records.

    Returns:
        dict with current fast status, durations, rolling averages, compliance.
    """
    from django.db.models import Avg, Sum

    from apps.health.models import FastingWindow

    now = get_current_time()
    today = now.date()
    state = {}

    # ── Current fast (active = ended_at is null) ─────────────────
    active_fast = (
        FastingWindow.objects.filter(user=user, ended_at__isnull=True, status="active")
        .order_by("-started_at")
        .first()
    )
    state["current_fast_active"] = active_fast is not None
    if active_fast:
        elapsed = (now - active_fast.started_at).total_seconds() / 3600
        state["current_fast_hours"] = round(elapsed, 1)

    # ── Last completed fast ──────────────────────────────────────
    last_fast = (
        FastingWindow.objects.filter(
            user=user, ended_at__isnull=False, status="active"
        )
        .order_by("-ended_at")
        .first()
    )
    if last_fast:
        duration = (last_fast.ended_at - last_fast.started_at).total_seconds() / 3600
        state["last_fast_duration"] = round(duration, 1)
        state["last_fast_end"] = last_fast.ended_at.isoformat()

    # ── Rolling 7-day fasting stats ──────────────────────────────
    cutoff_7d = now - timedelta(days=7)
    fasts_7d = FastingWindow.objects.filter(
        user=user,
        ended_at__isnull=False,
        started_at__gte=cutoff_7d,
        status="active",
    )
    fasts_7d_count = fasts_7d.count()
    state["fasts_7d"] = fasts_7d_count

    if fasts_7d_count > 0:
        # Calculate total fasting hours in 7 days
        total_hours = 0
        for fast in fasts_7d.values_list("started_at", "ended_at"):
            duration = (fast[1] - fast[0]).total_seconds() / 3600
            total_hours += duration
        state["rolling_7d_fasting_hours"] = round(total_hours, 1)
        state["rolling_7d_avg_fast_duration"] = round(total_hours / fasts_7d_count, 1)

    # ── Fasting compliance score (target vs actual) ──────────────
    # If user has a target_hours, measure compliance as actual/target
    # Otherwise, consistency-based: fasts this week / 7
    if fasts_7d_count > 0:
        # Use the most recent fast's target_hours as the protocol target
        recent_with_target = (
            FastingWindow.objects.filter(
                user=user,
                target_hours__isnull=False,
                status="active",
            )
            .order_by("-started_at")
            .values_list("target_hours", flat=True)
            .first()
        )
        if recent_with_target and recent_with_target > 0:
            avg_duration = state.get("rolling_7d_avg_fast_duration", 0)
            # Score: how close avg duration is to target (0-100)
            ratio = min(avg_duration / recent_with_target, 1.5)
            state["fasting_compliance_score"] = round(
                max(0, 100 - abs(100 - ratio * 100)), 1
            )
        else:
            # Consistency-based: daily fasting frequency
            state["fasting_compliance_score"] = round(
                min(fasts_7d_count / 7 * 100, 100), 1
            )

    return state


# ── Fitness State ───────────────────────────────────────────────


def build_fitness_state(user):
    """
    Build fitness state from actual database records.

    Returns:
        dict with workout counts, volume, duration, consistency, strength trends.
    """
    from django.db.models import Avg, Count, Sum

    from apps.health.models import ExerciseSet, PersonalRecord, WorkoutSession

    now = get_current_time()
    state = {}

    # ── Workout counts ───────────────────────────────────────────
    cutoff_7d = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    state["workouts_7d"] = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_7d.date(), status="active"
    ).count()

    state["workouts_30d"] = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_30d.date(), status="active"
    ).count()

    # ── Volume (7d) ──────────────────────────────────────────────
    recent_sessions = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_7d.date(), status="active"
    )
    total_volume = 0
    total_sets = 0
    for session in recent_sessions:
        for we in session.workout_exercises.all():
            for s in we.sets.all():
                if s.weight and s.reps:
                    total_volume += float(s.weight) * s.reps
                total_sets += 1
    state["total_volume_7d"] = round(total_volume, 1)
    state["total_sets_7d"] = total_sets

    # ── Workout aggregates (7d) for CoS context ──────────────────
    if state["workouts_7d"] > 0:
        workout_agg = recent_sessions.aggregate(
            total_cal=Sum("calories_burned"),
            total_min=Sum("duration_minutes"),
            avg_hr=Avg("avg_heart_rate"),
            total_dist=Sum("distance_miles"),
        )
        if workout_agg["total_cal"]:
            state["workout_calories_7d"] = workout_agg["total_cal"]
        if workout_agg["total_min"]:
            state["workout_minutes_7d"] = workout_agg["total_min"]
        if workout_agg["avg_hr"]:
            state["workout_avg_hr_7d"] = round(float(workout_agg["avg_hr"]))
        if workout_agg["total_dist"]:
            state["workout_distance_7d"] = round(float(workout_agg["total_dist"]), 1)

        # Recent workouts list (top 3)
        recent_list = recent_sessions.order_by("-date")[:3]
        state["recent_workouts"] = [
            {
                "name": w.name,
                "type": w.workout_type,
                "date": str(w.date),
                "minutes": w.duration_minutes,
                "calories": w.calories_burned,
                "avg_hr": w.avg_heart_rate,
            }
            for w in recent_list
        ]

    # ── Average workout duration ─────────────────────────────────
    sessions_with_duration = WorkoutSession.objects.filter(
        user=user,
        date__gte=cutoff_30d.date(),
        duration_minutes__isnull=False,
        status="active",
    )
    if sessions_with_duration.exists():
        avg = sessions_with_duration.aggregate(avg=Avg("duration_minutes"))["avg"]
        state["avg_workout_duration"] = round(float(avg), 1) if avg else None

    # ── Last workout date ────────────────────────────────────────
    last_workout = (
        WorkoutSession.objects.filter(user=user, status="active")
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if last_workout:
        state["last_workout_date"] = last_workout.isoformat()

    # ── Personal records (30d) ───────────────────────────────────
    state["prs_30d"] = PersonalRecord.objects.filter(
        user=user, achieved_date__gte=cutoff_30d.date()
    ).count()

    # ── Strength trend score ─────────────────────────────────────
    # Compare 7d volume to previous 7d volume
    prev_7d_start = cutoff_7d - timedelta(days=7)
    prev_sessions = WorkoutSession.objects.filter(
        user=user,
        date__gte=prev_7d_start.date(),
        date__lt=cutoff_7d.date(),
        status="active",
    )
    prev_volume = 0
    for session in prev_sessions:
        for we in session.workout_exercises.all():
            for s in we.sets.all():
                if s.weight and s.reps:
                    prev_volume += float(s.weight) * s.reps

    if prev_volume > 0 and total_volume > 0:
        ratio = total_volume / prev_volume
        if ratio > 1.05:
            state["strength_trend_score"] = "increasing"
        elif ratio < 0.95:
            state["strength_trend_score"] = "decreasing"
        else:
            state["strength_trend_score"] = "stable"
    elif total_volume > 0:
        state["strength_trend_score"] = "insufficient_data"

    # ── Workout consistency score ────────────────────────────────
    # Ratio of this week's workouts to last 4-week average
    weekly_avg_30d = state["workouts_30d"] / 4.0 if state["workouts_30d"] > 0 else 0
    if weekly_avg_30d > 0:
        consistency = min(state["workouts_7d"] / weekly_avg_30d, 1.5)
        state["workout_consistency_score"] = round(consistency * 100, 1)

    # ── Per-exercise progress analysis ─────────────────────────
    state["exercise_progress"] = _build_exercise_progress(user, cutoff_30d)

    return state


def _build_exercise_progress(user, cutoff_30d):
    """
    Build per-exercise progress analysis for the last 30 days.

    For each resistance exercise with ≥4 working sets in 30 days, computes:
    - session count, set count, PR count
    - e1RM trend (recent 14d vs prior 15-30d)
    - status: improving / plateau / regressing / new

    Returns list of dicts sorted by exercise name.
    """
    from collections import defaultdict

    from django.db.models import Count

    from apps.health.models import ExerciseSet, PersonalRecord
    from apps.health.pr_utils import brzycki_1rm

    cutoff_14d = get_current_time() - timedelta(days=14)

    # 1. Get all non-warmup resistance sets in the last 30 days
    sets_qs = ExerciseSet.objects.filter(
        workout_exercise__session__user=user,
        workout_exercise__session__date__gte=cutoff_30d.date(),
        workout_exercise__session__status="active",
        workout_exercise__exercise__category="resistance",
        is_warmup=False,
        weight__isnull=False,
        reps__isnull=False,
    ).select_related(
        "workout_exercise__exercise",
        "workout_exercise__session",
    )

    # Group sets by exercise
    exercise_data = defaultdict(lambda: {
        "sessions": set(),
        "sets_30d": 0,
        "recent_e1rms": [],   # last 14 days
        "prior_e1rms": [],    # 15-30 day window
    })

    for s in sets_qs:
        ex = s.workout_exercise.exercise
        session_date = s.workout_exercise.session.date
        data = exercise_data[ex]
        data["sessions"].add(s.workout_exercise.session_id)
        data["sets_30d"] += 1

        e1rm = brzycki_1rm(s.weight, s.reps)
        if session_date >= cutoff_14d.date():
            data["recent_e1rms"].append(e1rm)
        else:
            data["prior_e1rms"].append(e1rm)

    # 2. Get PR counts per exercise in the last 30 days
    pr_counts = dict(
        PersonalRecord.objects.filter(
            user=user,
            achieved_date__gte=cutoff_30d.date(),
        ).values_list("exercise_id").annotate(
            count=Count("id")
        ).values_list("exercise_id", "count")
    )

    # 3. Build progress list
    progress = []
    for exercise, data in exercise_data.items():
        # Minimum threshold: 4 working sets
        if data["sets_30d"] < 4:
            continue

        sessions_30d = len(data["sessions"])
        prs_30d = pr_counts.get(exercise.id, 0)

        recent_best = max(data["recent_e1rms"]) if data["recent_e1rms"] else 0
        prior_best = max(data["prior_e1rms"]) if data["prior_e1rms"] else 0

        # Determine trend
        if not data["prior_e1rms"]:
            trend = "new"
        elif prior_best > 0:
            ratio = recent_best / prior_best if recent_best > 0 else 0
            if ratio > 1.02:
                trend = "up"
            elif ratio < 0.95:
                trend = "down"
            else:
                trend = "flat"
        else:
            trend = "new"

        # Determine status
        if trend == "new":
            status = "new"
        elif prs_30d > 0 or trend == "up":
            status = "improving"
        elif trend == "down":
            status = "regressing"
        else:
            status = "plateau"

        progress.append({
            "exercise": exercise.name,
            "sessions_30d": sessions_30d,
            "sets_30d": data["sets_30d"],
            "prs_30d": prs_30d,
            "best_e1rm": round(max(recent_best, prior_best), 1),
            "recent_e1rm": round(recent_best, 1) if recent_best else None,
            "prior_e1rm": round(prior_best, 1) if prior_best else None,
            "trend": trend,
            "status": status,
        })

    progress.sort(key=lambda x: x["exercise"])
    return progress


# ── Transformation State (Composite — SAE only, no DB) ──────────


def build_transformation_state(user):
    """
    Build composite transformation state from OTHER SAE states.

    IMPORTANT: This builder MUST only use already-built state values.
    It must NEVER query database models directly.

    This builder reads from the UserState object directly (not via
    get_module_state) to avoid infinite recursion during full rebuilds.
    The other module states are guaranteed to be built before this one
    because transformation is registered last in MODULE_BUILDERS.

    Returns:
        dict with composite transformation scores (0-100).
    """
    from apps.core.ai_state.models import UserState

    state = {}

    # Read already-persisted state directly to avoid rebuild recursion.
    # During a full rebuild, the state_engine builds modules in order,
    # saving after each. By the time transformation runs, the other
    # modules are already in state_data.
    try:
        user_state = UserState.objects.get(user=user)
        all_state = user_state.state_data or {}
    except UserState.DoesNotExist:
        all_state = {}

    health = all_state.get("health", {})
    nutrition = all_state.get("nutrition", {})
    fasting = all_state.get("fasting", {})
    fitness = all_state.get("fitness", {})

    # ── Weight trend score (0-100) ───────────────────────────────
    weight_trend = health.get("weight_trend", "insufficient_data")
    weight_scores = {
        "decreasing": 80,
        "stable": 60,
        "increasing": 30,
        "insufficient_data": 0,
    }
    weight_trend_score = weight_scores.get(weight_trend, 0)
    if weight_trend_score > 0:
        state["weight_trend_score"] = weight_trend_score

    # ── Nutrition score (0-100) ──────────────────────────────────
    macro_compliance = nutrition.get("macro_compliance_score")
    nutrition_score = 0
    if macro_compliance is not None:
        nutrition_score = round(min(macro_compliance, 100))
    elif nutrition.get("food_entries_7d", 0) > 0:
        # Tracking but no targets — give partial credit
        nutrition_score = 40
    if nutrition_score > 0:
        state["nutrition_score"] = nutrition_score

    # ── Fasting score (0-100) ────────────────────────────────────
    fasting_compliance = fasting.get("fasting_compliance_score")
    fasting_score = round(fasting_compliance) if fasting_compliance is not None else 0
    if fasting_score > 0:
        state["fasting_score"] = fasting_score

    # ── Workout score (0-100) ────────────────────────────────────
    workout_consistency = fitness.get("workout_consistency_score")
    workout_score = 0
    if workout_consistency is not None:
        workout_score = round(min(workout_consistency, 100))
    elif fitness.get("workouts_7d", 0) > 0:
        workout_score = 40
    if workout_score > 0:
        state["workout_score"] = workout_score

    # ── Recovery score (0-100) ───────────────────────────────────
    # Based on sleep quality from health state
    sleep_avg = health.get("sleep_avg_duration_7d")
    recovery_score = 0
    if sleep_avg is not None:
        # 420-480 min (7-8 hours) = ideal
        if sleep_avg >= 420:
            recovery_score = min(100, round(sleep_avg / 480 * 100))
        else:
            recovery_score = round(sleep_avg / 420 * 70)  # Penalize under 7h
    if recovery_score > 0:
        state["recovery_score"] = recovery_score

    # ── Momentum score (0-100) ───────────────────────────────────
    # Based on consistency of activity across domains
    active_domains = 0
    if nutrition.get("food_entries_7d", 0) > 0:
        active_domains += 1
    if fasting.get("fasts_7d", 0) > 0:
        active_domains += 1
    if fitness.get("workouts_7d", 0) > 0:
        active_domains += 1
    if health.get("weight_entries_90d", 0) > 0:
        active_domains += 1
    if health.get("sleep_entries_7d", 0) > 0:
        active_domains += 1

    momentum_score = round(active_domains / 5 * 100) if active_domains > 0 else 0
    if momentum_score > 0:
        state["momentum_score"] = momentum_score

    # ── Composite transformation score (0-100) ───────────────────
    # Weighted average of all sub-scores
    weights = {
        "weight_trend_score": 0.20,
        "nutrition_score": 0.25,
        "workout_score": 0.25,
        "fasting_score": 0.10,
        "recovery_score": 0.10,
        "momentum_score": 0.10,
    }

    weighted_sum = 0
    total_weight = 0
    for key, weight in weights.items():
        val = state.get(key)
        if val is not None and val > 0:
            weighted_sum += val * weight
            total_weight += weight

    if total_weight > 0:
        state["transformation_score"] = round(weighted_sum / total_weight)

    return state


# ── Meals State Builder ──────────────────────────────────────────


def build_meals_state(user):
    """
    Build meals state from actual database records.

    Returns:
        dict with pantry summary, active meal plans, recent meal history.
    """
    from apps.meals.models import (
        DietaryProfile,
        Household,
        HouseholdMembership,
        MealPlanEntry,
        PantryItem,
    )

    now = get_current_time()
    state = {}

    # Find user's household
    membership = (
        HouseholdMembership.objects
        .filter(user=user)
        .select_related("household")
        .first()
    )

    if not membership:
        state["has_household"] = False
        return state

    household = membership.household
    state["has_household"] = True
    state["household_name"] = household.name
    state["grocery_cycle_days"] = household.grocery_cycle_days

    # Pantry summary
    pantry_count = PantryItem.objects.filter(
        household=household, quantity__gt=0,
    ).count()
    state["pantry_item_count"] = pantry_count

    expiring_count = PantryItem.objects.filter(
        household=household,
        quantity__gt=0,
        expiration_date_estimated__lte=(now + timedelta(days=3)).date(),
        expiration_date_estimated__gte=now.date(),
    ).count()
    state["pantry_expiring_count"] = expiring_count

    # Expiring item names (up to 5)
    if expiring_count > 0:
        state["expiring_item_names"] = list(
            PantryItem.objects.filter(
                household=household,
                quantity__gt=0,
                expiration_date_estimated__lte=(now + timedelta(days=3)).date(),
                expiration_date_estimated__gte=now.date(),
            ).values_list("ingredient__canonical_name", flat=True)[:5]
        )

    # Active meal plan
    today = now.date()
    active_entry = MealPlanEntry.objects.filter(
        meal_plan__household=household,
        date=today,
        meal_type="dinner",
    ).select_related("recipe").first()

    state["has_dinner_planned"] = active_entry is not None
    if active_entry:
        state["dinner_recipe"] = active_entry.recipe.title

    # Dietary profile
    try:
        profile = DietaryProfile.objects.get(user=user)
        state["has_dietary_profile"] = True
        state["diabetes_sensitive"] = profile.diabetes_sensitive
        if profile.carb_limit_daily:
            state["carb_limit_daily"] = float(profile.carb_limit_daily)
        if profile.protein_target_daily:
            state["protein_target_daily"] = float(profile.protein_target_daily)
    except DietaryProfile.DoesNotExist:
        state["has_dietary_profile"] = False

    return state


# ── Intervention State Builder ────────────────────────────────────


def build_intervention_state(user):
    """
    Build intervention/governance state from InterventionLog records.

    Returns:
        dict with override frequencies, renegotiation patterns, tier 1 skips.
    """
    from django.db.models import Count

    now = get_current_time()
    state = {}

    seven_days_ago = now - timedelta(days=7)
    ten_days_ago = now - timedelta(days=10)
    fourteen_days_ago = now - timedelta(days=14)

    try:
        from apps.core.blueprint.models import InterventionLog

        # Override frequency (14d)
        state["override_frequency_14d"] = InterventionLog.objects.filter(
            user=user, user_response="proceeded",
            created_at__gte=fourteen_days_ago,
        ).count()

        # Override count (10d)
        state["override_count_10d"] = InterventionLog.objects.filter(
            user=user, user_response="proceeded",
            created_at__gte=ten_days_ago,
        ).count()

        # Pending friction gates
        state["pending_friction_gates"] = InterventionLog.objects.filter(
            user=user, level=4, user_response="pending",
        ).count()

        # Deferrals (7d)
        state["deferrals_7d"] = InterventionLog.objects.filter(
            user=user, created_at__gte=seven_days_ago,
            user_response__in=["proceeded", "dismissed"],
        ).count()

        # Renegotiation patterns (10d)
        patterns = list(
            InterventionLog.objects.filter(
                user=user, created_at__gte=ten_days_ago,
                user_response__in=["proceeded", "dismissed"],
                behavior_key__gt="",
            )
            .values("behavior_key")
            .annotate(count=Count("id"))
            .filter(count__gte=3)
            .order_by("-count")[:5]
        )
        state["renegotiation_patterns"] = [
            {"behavior": p["behavior_key"], "count": p["count"], "window_days": 10}
            for p in patterns
        ]

        # Tier 1 skip patterns (7d)
        tier1_records = list(
            InterventionLog.objects.filter(
                user=user, created_at__gte=seven_days_ago,
                trigger_type__in=["tier1_violation", "non_negotiable_miss"],
            ).values("behavior_key", "created_at")
        )
        tier1_by_behavior = {}
        tier1_dates = []
        for rec in tier1_records:
            key = rec["behavior_key"] or "general"
            tier1_by_behavior.setdefault(key, 0)
            tier1_by_behavior[key] += 1
            tier1_dates.append(rec["created_at"].date())

        state["tier1_skip_patterns"] = [
            {"behavior": bkey, "count": count, "window_days": 7}
            for bkey, count in tier1_by_behavior.items()
            if count >= 2
        ]

        # Consecutive tier 1 skips
        if tier1_dates:
            unique_dates = sorted(set(tier1_dates), reverse=True)
            consecutive = 1
            for i in range(1, len(unique_dates)):
                if (unique_dates[i - 1] - unique_dates[i]).days <= 1:
                    consecutive += 1
                else:
                    break
            state["consecutive_tier1_skips"] = consecutive

    except Exception:
        logger.warning("Intervention state build failed", exc_info=True)

    return state


# ── Feedback State Builder ────────────────────────────────────────


def build_feedback_state(user):
    """
    Build feedback profile state from engagement/effectiveness models.

    Returns:
        dict with insight engagement, briefing rates, intervention effectiveness.
    """
    state = {}

    try:
        from apps.core.ai_feedback.models import (
            BriefingEngagementProfile,
            InsightEngagementProfile,
            InterventionEffectivenessProfile,
        )

        ie = InsightEngagementProfile.objects.filter(user=user).first()
        be = BriefingEngagementProfile.objects.filter(user=user).first()
        iv = InterventionEffectivenessProfile.objects.filter(user=user).first()

        state["insight_engagement"] = ie.engagement_score if ie else 0.5
        state["briefing_open_rate"] = be.open_rate if be else 0.0
        state["preferred_briefing_length"] = be.preferred_length if be else "standard"
        state["intervention_effectiveness"] = iv.effectiveness_score if iv else 0.5
        state["escalation_modifier"] = iv.escalation_speed_modifier if iv else 0.0

    except Exception:
        logger.warning("Feedback state build failed", exc_info=True)

    return state


# ── Life Events State Builder ─────────────────────────────────────


def build_life_events_state(user):
    """
    Build approaching life events state (14-day window).

    Returns:
        dict with approaching_events list.
    """
    state = {}
    approaching = []

    try:
        from apps.core.utils import get_user_today

        today = get_user_today(user)

        try:
            from apps.life.models import LifeEvent, SignificantEvent

            for event in SignificantEvent.objects.filter(user=user):
                try:
                    days_until = event.days_until_next(today)
                    if days_until is not None and days_until <= 14:
                        event_info = {
                            "title": event.title,
                            "type": event.event_type,
                            "days_until": days_until,
                            "person": event.person_name or "",
                        }
                        if event.original_year:
                            event_info["years"] = today.year - event.original_year
                        approaching.append(event_info)
                except Exception:
                    continue

            cutoff = today + timedelta(days=14)
            for event in LifeEvent.objects.filter(
                user=user, start_date__gte=today, start_date__lte=cutoff,
            ).exclude(status="deleted").order_by("start_date")[:10]:
                approaching.append({
                    "title": event.title,
                    "type": getattr(event, "event_type", "event"),
                    "days_until": (event.start_date - today).days,
                    "person": "",
                })

            approaching.sort(key=lambda e: e["days_until"])
        except Exception:
            pass

    except Exception:
        logger.warning("Life events state build failed", exc_info=True)

    state["approaching_events"] = approaching[:5]
    return state


# ── Scan State Builder ────────────────────────────────────────────


def build_scan_state(user):
    """
    Build recent image analysis state (7-day window).

    Returns:
        dict with recent_analyses list.
    """
    state = {"recent_analyses": []}

    try:
        from apps.scan.models import ImageAnalysis

        lookback = get_current_time() - timedelta(days=7)
        analyses = ImageAnalysis.objects.filter(
            user=user, status="completed", created_at__gte=lookback,
        ).order_by("-created_at")[:10]

        state["recent_analyses"] = [
            {
                "summary": a.summary,
                "category": a.category,
                "source": a.get_source_type_display(),
                "when": a.created_at.isoformat(),
                "tags": a.relevance_tags[:5] if a.relevance_tags else [],
            }
            for a in analyses
        ]
    except Exception:
        logger.warning("Scan state build failed", exc_info=True)

    return state


# ── Governance State Builder ──────────────────────────────────────


def build_governance_state(user):
    """
    Build governance-related state (priorities, drift scenarios).

    Returns:
        dict with declared_priorities and drift_scenario_count_14d.
    """
    state = {"declared_priorities": [], "drift_scenario_count_14d": 0}

    # Declared priorities
    try:
        from apps.core.blueprint.models import UserPriorityProfile

        priorities = UserPriorityProfile.objects.filter(user=user)
        state["declared_priorities"] = [
            {
                "module": p.module_key,
                "sub_module": p.sub_module_key,
                "level": p.get_declared_priority_level_display(),
                "weight": float(p.importance_weight),
                "reason": p.declared_reason[:200] if p.declared_reason else "",
            }
            for p in priorities
        ]
    except Exception:
        logger.warning("Governance priorities build failed", exc_info=True)

    # Drift scenario frequency (14d)
    try:
        from apps.core.ai_arbitration.models import ScenarioHistory

        cutoff = get_current_time() - timedelta(days=14)
        state["drift_scenario_count_14d"] = ScenarioHistory.objects.filter(
            user=user, date__gte=cutoff.date(),
            dominant_scenario="DRIFT_CRITICAL",
        ).count()
    except Exception:
        logger.warning("Governance drift scenarios build failed", exc_info=True)

    return state


# ── Task Commitment State ────────────────────────────────────────

def build_task_state(user):
    """
    Build task commitment state from actual database records.

    Returns:
        dict with task_commitment_summary (totals, 7d counts, consistency_score),
        nn_skip_streaks (top 5 NN tasks with active streaks),
        active_tasks_by_level, and overdue_nn_count.
    """
    from apps.life.models import Task
    from django.db.models import Count, Q

    now = get_current_time()
    state = {}

    try:
        # Active tasks by commitment level
        level_counts = (
            Task.objects.filter(user=user, status='active', completion_status='pending')
            .values('commitment_level')
            .annotate(count=Count('id'))
        )
        by_level = {'optional': 0, 'important': 0, 'non_negotiable': 0}
        for entry in level_counts:
            level = entry['commitment_level']
            if level in by_level:
                by_level[level] = entry['count']
        state['active_tasks_by_level'] = by_level

        # 7-day window for consistency score
        seven_days_ago = now - timedelta(days=7)

        nn_completed_7d = Task.objects.filter(
            user=user,
            commitment_level='non_negotiable',
            completion_status='completed',
            completed_at__gte=seven_days_ago,
        ).count()

        nn_skipped_7d = Task.objects.filter(
            user=user,
            commitment_level='non_negotiable',
            completion_status='skipped',
            last_skipped_at__gte=seven_days_ago,
        ).count()

        total_acted = nn_completed_7d + nn_skipped_7d
        consistency = round(nn_completed_7d / total_acted, 2) if total_acted > 0 else 0.0

        nn_total = Task.objects.filter(
            user=user,
            commitment_level='non_negotiable',
            status='active',
            completion_status='pending',
        ).count()

        state['task_commitment_summary'] = {
            'non_negotiable_total': nn_total,
            'non_negotiable_completed_7d': nn_completed_7d,
            'non_negotiable_skipped_7d': nn_skipped_7d,
            'consistency_score': consistency,
        }

        # Top 5 NN tasks with active skip streaks (recency-guarded)
        nn_streak_tasks = Task.objects.filter(
            user=user,
            commitment_level='non_negotiable',
            skip_streak__gte=1,
            status='active',
        ).order_by('-skip_streak')[:5]

        nn_skip_streaks = []
        for task in nn_streak_tasks:
            eff = task.effective_skip_streak
            if eff > 0:
                nn_skip_streaks.append({'task': task.title, 'streak': eff})
        state['nn_skip_streaks'] = nn_skip_streaks

        # Overdue NN tasks
        today = now.date() if hasattr(now, 'date') else now
        overdue_nn = Task.objects.filter(
            user=user,
            commitment_level='non_negotiable',
            completion_status='pending',
            status='active',
            due_date__lt=today,
        ).count()
        state['overdue_nn_count'] = overdue_nn

    except Exception:
        logger.warning("Task commitment state build failed", exc_info=True)

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
    "nutrition": build_nutrition_state,
    "fasting": build_fasting_state,
    "fitness": build_fitness_state,
    "transformation": build_transformation_state,
    "meals": build_meals_state,
    "intervention": build_intervention_state,
    "feedback": build_feedback_state,
    "life_events": build_life_events_state,
    "scan": build_scan_state,
    "governance": build_governance_state,
    "tasks": build_task_state,
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
