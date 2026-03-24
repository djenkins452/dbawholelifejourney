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


def _build_state_meta(completeness='full', confidence='high'):
    """Build standardized meta block for SAE state contract.

    Every domain builder should include this in its return dict under
    the '_meta' key. This enables Beth to reason about state reliability.

    Args:
        completeness: 'full' | 'partial' | 'limited'
        confidence: 'high' | 'medium' | 'low'
    """
    return {
        'last_updated': get_current_time().isoformat(),
        'source': 'SAE',
        'completeness': completeness,
        'confidence': confidence,
    }


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

    # ── Heart Rate (7-day avg + latest) ─────────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import HeartRateEntry

        hr_avg = HeartRateEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("bpm"))["avg"]
        if hr_avg:
            state["heart_rate_avg_7d"] = round(float(hr_avg))

        latest_hr = (
            HeartRateEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values_list("bpm", "recorded_at")
            .first()
        )
        if latest_hr:
            state["latest_heart_rate"] = latest_hr[0]
            state["last_heart_rate_entry"] = latest_hr[1].isoformat()
    except Exception:
        pass

    # ── Glucose (7-day avg + latest) ──────────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import GlucoseEntry

        glucose_avg = GlucoseEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("value"))["avg"]
        if glucose_avg:
            state["glucose_avg_7d"] = round(float(glucose_avg))

        latest_glucose = (
            GlucoseEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values_list("value", "unit", "recorded_at")
            .first()
        )
        if latest_glucose:
            state["latest_glucose"] = float(latest_glucose[0])
            state["latest_glucose_unit"] = latest_glucose[1]
            state["last_glucose_entry"] = latest_glucose[2].isoformat()
    except Exception:
        pass

    # ── Blood Oxygen (7-day avg + latest) ─────────────────────
    try:
        from django.db.models import Avg
        from apps.health.models import BloodOxygenEntry

        spo2_avg = BloodOxygenEntry.objects.filter(
            user=user, recorded_at__gte=cutoff_7d
        ).aggregate(avg=Avg("spo2"))["avg"]
        if spo2_avg:
            state["blood_oxygen_avg_7d"] = round(float(spo2_avg), 1)

        latest_spo2 = (
            BloodOxygenEntry.objects.filter(user=user)
            .order_by("-recorded_at")
            .values_list("spo2", "recorded_at")
            .first()
        )
        if latest_spo2:
            state["latest_blood_oxygen"] = float(latest_spo2[0])
            state["last_blood_oxygen_entry"] = latest_spo2[1].isoformat()
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
        # Use date comparison, not datetime, to prevent a reading at 9pm
        # yesterday showing as "0 days since reading" at 6am today.
        state["days_since_reading"] = (now.date() - last_reading.date()).days

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

    # ── Mood trend (7-day, directional) ──────────────────────────
    # Required by cross-domain rules: MotivationDriftRule,
    # FinancialAnxietyRule, BehavioralInstabilityRule.
    # Without this, those rules silently get default "stable" and never fire.
    _MOOD_SCORES = {'great': 5, 'good': 4, 'okay': 3, 'low': 2, 'difficult': 1}
    cutoff_7d = now - timedelta(days=7)
    moods_7d = list(
        JournalEntry.objects.filter(
            user=user,
            entry_date__gte=cutoff_7d.date(),
            mood__isnull=False,
        )
        .exclude(mood="")
        .order_by("entry_date")
        .values_list("mood", flat=True)
    )
    state["entries_7d"] = len(moods_7d)
    if len(moods_7d) >= 3:
        scores = [_MOOD_SCORES.get(m, 3) for m in moods_7d]
        avg = sum(scores) / len(scores)
        state["mood_avg_7d"] = round(avg, 1)
        # Directional trend: compare first half vs second half
        mid = len(scores) // 2
        first_half_avg = sum(scores[:mid]) / max(mid, 1)
        second_half_avg = sum(scores[mid:]) / max(len(scores) - mid, 1)
        diff = second_half_avg - first_half_avg
        if diff < -0.5:
            state["mood_trend"] = "declining"
        elif diff > 0.5:
            state["mood_trend"] = "improving"
        else:
            state["mood_trend"] = "stable"
    else:
        state["mood_avg_7d"] = None
        state["mood_trend"] = "stable"  # Insufficient data — safe default

    # ── Emotion counts (7-day, structured M2M selections) ────────
    # Provides emotion_counts_7d for downstream signal generation
    # and cross-domain rules (e.g., anxiety_mention_count_7d).
    state["emotion_counts_7d"] = {}
    state["anxiety_mention_count_7d"] = 0
    try:
        from django.db.models import Count as _Count
        emotion_counts = dict(
            JournalEntry.objects.filter(
                user=user,
                entry_date__gte=cutoff_7d.date(),
                emotions__isnull=False,
            )
            .values_list('emotions__slug')
            .annotate(cnt=_Count('id'))
            .values_list('emotions__slug', 'cnt')
        )
        if emotion_counts:
            state["emotion_counts_7d"] = emotion_counts
            # Convenience: anxiety_mention_count_7d for FinancialAnxietyRule
            state["anxiety_mention_count_7d"] = (
                emotion_counts.get('anxious', 0)
                + emotion_counts.get('stressed', 0)
                + emotion_counts.get('overwhelmed', 0)
            )
    except Exception:
        pass  # Defaults already set above

    # ── Rolling stress score (14-day, decay-based persistence) ───
    # Uses exponential decay to detect sustained stress vs. one-off bad days.
    # Computed from per-day stress emotion counts over 14 days.
    state["stress_score"] = None
    try:
        from django.db.models import Count as _StressCount
        from apps.core.ai_insights.pattern_utils import compute_rolling_stress_score

        _stress_slugs = ['stressed', 'anxious', 'overwhelmed']
        cutoff_14d = now - timedelta(days=14)

        # Get per-day stress emotion counts
        daily_stress = list(
            JournalEntry.objects.filter(
                user=user,
                entry_date__gte=cutoff_14d.date(),
                emotions__slug__in=_stress_slugs,
            )
            .values_list('entry_date')
            .annotate(stress_count=_StressCount('id'))
            .order_by('entry_date')
        )
        if daily_stress:
            # Normalize: each stress emotion selection = 0.4 weight
            daily_values = [(d, min(count * 0.4, 1.0)) for d, count in daily_stress]
            stress_result = compute_rolling_stress_score(daily_values)
            state["stress_score"] = stress_result
    except Exception:
        pass  # stress_score remains None — no harm

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

    # Only count sessions with completed_at set — a session without
    # completed_at was created (template/HealthKit) but never performed.
    # Matches fitness_utils.get_weekly_volume() which uses completed_at__isnull=False.
    state["workouts_7d"] = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_7d.date(), status="active",
        completed_at__isnull=False,
    ).count()

    state["workouts_30d"] = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_30d.date(), status="active",
        completed_at__isnull=False,
    ).count()

    # ── Volume (7d) ──────────────────────────────────────────────
    recent_sessions = WorkoutSession.objects.filter(
        user=user, date__gte=cutoff_7d.date(), status="active",
        completed_at__isnull=False,
    ).prefetch_related('workout_exercises__sets')
    total_volume = 0
    total_movement_work = 0
    total_sets = 0
    for session in recent_sessions:
        for we in session.workout_exercises.all():
            for s in we.sets.all():
                v = s.volume
                if v is not None:
                    total_volume += v
                mw = s.movement_work
                if mw is not None:
                    total_movement_work += mw
                total_sets += 1
    state["total_volume_7d"] = round(total_volume, 1)
    state["movement_work_7d"] = total_movement_work
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
        WorkoutSession.objects.filter(
            user=user, status="active", completed_at__isnull=False
        )
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
    ).prefetch_related('workout_exercises__sets')
    prev_volume = 0
    prev_movement_work = 0
    for session in prev_sessions:
        for we in session.workout_exercises.all():
            for s in we.sets.all():
                v = s.volume
                if v is not None:
                    prev_volume += v
                mw = s.movement_work
                if mw is not None:
                    prev_movement_work += mw

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
        "recent_weights": [],  # raw weights last 14 days
        "prior_weights": [],   # raw weights 15-30 day window
    })

    for s in sets_qs:
        ex = s.workout_exercise.exercise
        session_date = s.workout_exercise.session.date
        data = exercise_data[ex]
        data["sessions"].add(s.workout_exercise.session_id)
        data["sets_30d"] += 1

        e1rm = brzycki_1rm(s.weight, s.reps)
        w = float(s.weight)
        if session_date >= cutoff_14d.date():
            data["recent_e1rms"].append(e1rm)
            data["recent_weights"].append(w)
        else:
            data["prior_e1rms"].append(e1rm)
            data["prior_weights"].append(w)

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

        # Raw weight progression: catches the case where a user moves
        # from 135 lbs → 145 lbs but drops reps, causing e1RM to look
        # flat.  A meaningful jump in max working weight is still progress.
        recent_max_weight = max(data["recent_weights"]) if data["recent_weights"] else 0
        prior_max_weight = max(data["prior_weights"]) if data["prior_weights"] else 0

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
                # e1RM is flat — check raw weight as secondary signal.
                # If max working weight went up by ≥3% (or ≥5 lbs for
                # lighter lifts), treat as progressing, not plateauing.
                weight_ratio = (
                    recent_max_weight / prior_max_weight
                    if prior_max_weight > 0 else 0
                )
                weight_delta = recent_max_weight - prior_max_weight
                if weight_ratio > 1.03 or weight_delta >= 5:
                    trend = "up"
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

    # Today's events (separate key for Beth to reference directly)
    state["today_events"] = [
        e for e in approaching if e["days_until"] == 0
    ]

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

    Returns dict with flat keys (operational interface) + _contract overlay.
    See docs/SAE_STATE_CONTRACT.md for mapping table and migration plan.

    Contract sections: summary, today, upcoming, alerts
    For new consumers, prefer reading _contract over flat keys.
    """
    from apps.life.models import Task
    from django.db.models import Count, Q

    now = get_current_time()
    state = {}

    try:
        # Active tasks by commitment level — canonical query
        from apps.life.services.task_queries import TaskQueries
        level_counts = (
            TaskQueries.pending(user)
            .values('commitment_level')
            .annotate(count=Count('id'))
        )
        by_level = {'foundational': 0, 'important': 0, 'flexible': 0}
        for entry in level_counts:
            level = entry['commitment_level']
            if level in by_level:
                by_level[level] = entry['count']
        state['active_tasks_by_level'] = by_level

        # 7-day window for consistency score
        seven_days_ago = now - timedelta(days=7)

        nn_agg = Task.objects.filter(
            user=user,
            commitment_level='foundational',
        ).aggregate(
            completed_7d=Count('id', filter=Q(
                completion_status='completed',
                completed_at__gte=seven_days_ago,
            )),
            skipped_7d=Count('id', filter=Q(
                completion_status='skipped',
                last_skipped_at__gte=seven_days_ago,
            )),
            active_pending=Count('id', filter=Q(
                status='active',
                completion_status='pending',
            )),
        )
        nn_completed_7d = nn_agg['completed_7d']
        nn_skipped_7d = nn_agg['skipped_7d']
        nn_total = nn_agg['active_pending']

        total_acted = nn_completed_7d + nn_skipped_7d
        consistency = round(nn_completed_7d / total_acted, 2) if total_acted > 0 else 0.0

        state['task_commitment_summary'] = {
            'foundational_total': nn_total,
            'foundational_completed_7d': nn_completed_7d,
            'foundational_skipped_7d': nn_skipped_7d,
            'consistency_score': consistency,
        }

        # Top 5 NN tasks with active skip streaks (recency-guarded)
        nn_streak_tasks = Task.objects.filter(
            user=user,
            commitment_level='foundational',
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
            commitment_level='foundational',
            completion_status='pending',
            status='active',
            due_date__lt=today,
        ).count()
        state['overdue_nn_count'] = overdue_nn

        # ── Date-based priority binning ──
        from apps.core.utils import get_user_today
        user_today = get_user_today(user)
        tomorrow = user_today + timedelta(days=1)

        pending_qs = Task.objects.filter(
            user=user, status='active', completion_status='pending',
        )

        priority_counts = (
            pending_qs.values('priority')
            .annotate(count=Count('id'))
        )
        by_priority = {'now': 0, 'soon': 0, 'someday': 0}
        for entry in priority_counts:
            p = entry['priority']
            if p in by_priority:
                by_priority[p] = entry['count']
        state['tasks_now'] = by_priority['now']
        state['tasks_soon'] = by_priority['soon']
        state['tasks_someday'] = by_priority['someday']

        # Overdue (all commitment levels)
        state['overdue_count'] = pending_qs.filter(
            due_date__lt=user_today,
        ).count()

        # Due tomorrow
        state['due_tomorrow_count'] = pending_qs.filter(
            due_date=tomorrow,
        ).count()

        # ── Completed today (structured with momentum signal) ──
        _completed_qs = Task.objects.filter(
            user=user, completion_status='completed',
            completed_at__date=user_today,
        )
        _completed_count = _completed_qs.count()
        _completed_titles = list(
            _completed_qs.values_list('title', flat=True)[:10]
        )
        # Momentum signal: high(>=5), medium(2-4), low(0-1)
        if _completed_count >= 5:
            _momentum = 'high'
        elif _completed_count >= 2:
            _momentum = 'medium'
        else:
            _momentum = 'low'
        state['completed_today'] = _completed_count
        state['completed_today_titles'] = _completed_titles
        state['completed_today_detail'] = {
            'count': _completed_count,
            'titles': _completed_titles,
            'momentum_signal': _momentum,
        }

        # ── Time-aware classification helpers ──
        from apps.core.utils import get_user_now
        user_now = get_user_now(user)
        current_time = user_now.time()

        # Importance ordering: foundational > important > flexible
        _COMMIT_ORDER = {'foundational': 0, 'important': 1, 'flexible': 2}
        _PRIORITY_ORDER = {'now': 0, 'soon': 1, 'someday': 2}

        def _classify_time_proximity(scheduled_time, _user_now):
            """Classify task time proximity relative to now.

            Returns: 'overdue', 'due_now', 'due_soon', 'later_today', or 'unscheduled'.
            Uses real datetime comparison — no synthetic reference dates.
            """
            if scheduled_time is None:
                return 'unscheduled'
            from datetime import datetime as _dt
            sched_dt = _dt.combine(_user_now.date(), scheduled_time)
            now_dt = _dt.combine(_user_now.date(), _user_now.time())
            delta_min = (sched_dt - now_dt).total_seconds() / 60
            if delta_min < 0:
                return 'overdue'  # safety fallback; these are normally in time_overdue bucket
            elif delta_min <= 60:
                return 'due_now'
            elif delta_min <= 180:
                return 'due_soon'
            return 'later_today'

        def _serialize_task(t, overdue_reason=None, time_proximity=None):
            """Serialize a Task into a JSON-safe dict for SAE state."""
            entry = {
                'id': t.id,
                'title': t.title,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'scheduled_time': (
                    t.scheduled_time.strftime('%H:%M')
                    if t.scheduled_time else None
                ),
                'priority': t.priority,
                'commitment_level': t.commitment_level,
            }
            if overdue_reason:
                entry['overdue_reason'] = overdue_reason
            if time_proximity:
                entry['time_proximity'] = time_proximity
            return entry

        # ── OVERDUE + TODAY: unified grace-aware classification ──
        # Uses centralized classify_time_status() — single source of truth.
        from apps.core.utils import classify_time_status

        # Date-overdue: due_date < today (no time check needed)
        date_overdue = list(pending_qs.filter(
            due_date__isnull=False, due_date__lt=user_today,
        ).order_by('due_date', 'scheduled_time', '-created_at')[:25])

        # Today's tasks: classify each with grace-aware time logic
        today_all = list(pending_qs.filter(
            due_date=user_today,
        ).order_by('scheduled_time', '-created_at')[:50])

        time_overdue_today = []
        today_remaining = []
        for t in today_all:
            result = classify_time_status(
                t.due_date, t.scheduled_time, user_now,
                grace_minutes=getattr(t, 'grace_minutes', 0),
            )
            if result['status'] == 'overdue':
                time_overdue_today.append(t)
            else:
                today_remaining.append(t)

        all_overdue = [
            _serialize_task(t, overdue_reason='past_due_date') for t in date_overdue
        ] + [
            _serialize_task(t, overdue_reason='missed_scheduled_time') for t in time_overdue_today
        ]
        state['overdue_tasks'] = all_overdue
        state['overdue_count'] = len(all_overdue)

        # Sort today's tasks with intelligent ordering
        def _today_sort_key(t):
            return (
                # 1. Tasks with scheduled_time first (ascending), nulls last
                (0 if t.scheduled_time else 1),
                t.scheduled_time or '',
                # 2. Higher commitment first
                _COMMIT_ORDER.get(t.commitment_level, 2),
                # 3. Higher priority first
                _PRIORITY_ORDER.get(t.priority, 2),
            )

        today_remaining.sort(key=_today_sort_key)
        state['due_today_tasks_detail'] = [
            _serialize_task(
                t,
                time_proximity=_classify_time_proximity(t.scheduled_time, user_now),
            )
            for t in today_remaining
        ]

        # Legacy key (title list) — maintained for backward compat
        state['tasks_due_today'] = [t.title for t in today_remaining][:10]

        # ── TOMORROW / FUTURE / NO DATE ──
        state['due_tomorrow_tasks'] = [
            _serialize_task(t) for t in pending_qs.filter(
                due_date=tomorrow,
            ).order_by('scheduled_time', '-created_at')[:25]
        ]

        state['future_tasks'] = [
            _serialize_task(t) for t in pending_qs.filter(
                due_date__isnull=False, due_date__gt=tomorrow,
            ).order_by('due_date', 'scheduled_time', '-created_at')[:25]
        ]

        state['no_due_date_tasks'] = [
            _serialize_task(t) for t in pending_qs.filter(
                due_date__isnull=True,
            ).order_by('-created_at')[:25]
        ]

        # ── NEXT UP TASK (single most actionable task) ──
        # Selection rules:
        # 1. Highest-urgency overdue task
        # 2. Earliest upcoming scheduled task today
        # 3. Highest commitment/priority task today
        # 4. Fallback: any pending task
        next_up = None

        if all_overdue:
            # Pick the most urgent overdue: NN > important > optional,
            # then earliest due_date, then earliest scheduled_time
            best_overdue = min(all_overdue, key=lambda t: (
                _COMMIT_ORDER.get(t.get('commitment_level', 'optional'), 2),
                t.get('due_date') or '9999',
                t.get('scheduled_time') or '99:99',
            ))
            reason = best_overdue.get('overdue_reason', 'overdue')
            next_up = {**best_overdue, 'reason': reason}
        elif today_remaining:
            # Earliest scheduled or highest commitment today
            best_today = today_remaining[0]  # already sorted by _today_sort_key
            proximity = _classify_time_proximity(best_today.scheduled_time, user_now)
            if proximity == 'due_now':
                reason = 'due_now'
            elif proximity == 'due_soon':
                reason = 'due_soon'
            elif best_today.scheduled_time:
                reason = 'next_scheduled'
            else:
                reason = 'highest_commitment'
            next_up = {
                **_serialize_task(best_today, time_proximity=proximity),
                'reason': reason,
            }
        else:
            # Fallback: pick from tomorrow or no-date
            for fallback_bucket in [
                state.get('due_tomorrow_tasks', []),
                state.get('no_due_date_tasks', []),
            ]:
                if fallback_bucket:
                    next_up = {**fallback_bucket[0], 'reason': 'fallback'}
                    break

        state['next_up_task'] = next_up

    except Exception:
        logger.warning("Task commitment state build failed", exc_info=True)

    # ── Rich State Contract ──
    state['_contract'] = {
        'summary': {
            'total_pending': (
                state.get('tasks_now', 0)
                + state.get('tasks_soon', 0)
                + state.get('tasks_someday', 0)
            ),
            'by_priority': {
                'now': state.get('tasks_now', 0),
                'soon': state.get('tasks_soon', 0),
                'someday': state.get('tasks_someday', 0),
            },
            'by_level': state.get('active_tasks_by_level', {}),
            'completed_today': state.get('completed_today', 0),
            'momentum_signal': state.get('completed_today_detail', {}).get(
                'momentum_signal', 'low'
            ),
            'nn_consistency_score': state.get(
                'task_commitment_summary', {}
            ).get('consistency_score', 0),
        },
        'today': {
            'items': state.get('due_today_tasks_detail', []),
            'next_up': state.get('next_up_task'),
            'completed': state.get('completed_today_detail', {}),
        },
        'upcoming': {
            'tomorrow': state.get('due_tomorrow_tasks', []),
            'future': state.get('future_tasks', []),
            'no_due_date': state.get('no_due_date_tasks', []),
        },
        'alerts': {
            'overdue': state.get('overdue_tasks', []),
            'overdue_count': state.get('overdue_count', 0),
            'nn_skip_streaks': state.get('nn_skip_streaks', []),
        },
    }
    state['_meta'] = _build_state_meta(
        completeness='full',
        confidence='high',
    )
    return state


# ── Medicine State Builder ───────────────────────────────────────


def build_medicine_state(user):
    """
    Build medicine state from actual database records.

    Returns dict with flat keys (operational interface) + _contract overlay.
    See docs/SAE_STATE_CONTRACT.md for mapping table and migration plan.

    Contract sections: summary, today, upcoming, alerts
    For new consumers, prefer reading _contract over flat keys.
    """
    state = {}

    try:
        from apps.core.utils import get_user_now, get_user_today
        from apps.health.models import Medicine, MedicineLog, MedicineSchedule
        from apps.health.medicine_utils import calculate_medicine_adherence_rate

        user_today = get_user_today(user)
        user_now = get_user_now(user)
        current_time = user_now.time()

        # Active medicines summary
        active_meds = Medicine.objects.filter(
            user=user, medicine_status='active',
        ).prefetch_related('schedules')
        state['active_count'] = active_meds.count()
        state['active_medicines'] = list(
            active_meds.values_list('name', flat=True)[:15]
        )

        # Refill alerts
        needs_refill = [
            m.name for m in active_meds
            if m.needs_refill
        ]
        if needs_refill:
            state['needs_refill'] = needs_refill

        # Today's logs — batch fetch for per-schedule detail
        today_logs = MedicineLog.objects.filter(
            medicine__user=user,
            scheduled_date=user_today,
        ).select_related('medicine', 'schedule')
        state['today_taken'] = today_logs.filter(
            log_status__in=['taken', 'late'],
        ).count()
        state['today_missed'] = today_logs.filter(
            log_status='missed',
        ).count()
        state['today_pending'] = today_logs.filter(
            log_status='pending',
        ).count() if today_logs.filter(log_status='pending').exists() else 0

        # Build per-schedule operational detail for today
        # Index today's logs by (medicine_id, schedule_id) for O(1) lookup
        log_index = {}
        for log in today_logs:
            key = (log.medicine_id, log.schedule_id)
            log_index[key] = log

        weekday = user_today.weekday()  # 0=Monday
        expected_today = 0
        schedule_status = []

        # Use centralized time classification (same as routines + tasks)
        from apps.core.utils import classify_time_status

        for med in active_meds:
            for sched in med.schedules.filter(is_active=True):
                if not sched.applies_to_day(weekday):
                    continue
                expected_today += 1

                # Look up today's log for this schedule
                log = log_index.get((med.id, sched.id))
                if log and log.log_status in ('taken', 'late'):
                    status = 'taken'
                    log_time = (
                        log.completed_at.astimezone(user_now.tzinfo).strftime('%I:%M %p').lstrip('0')
                        if log.completed_at else None
                    )
                elif log and log.log_status == 'missed':
                    status = 'missed'
                    log_time = None
                else:
                    # Centralized: classify_time_status handles grace-aware overdue
                    ts = classify_time_status(
                        user_today, sched.scheduled_time, user_now,
                        grace_minutes=0,  # medications have no grace period yet
                    )
                    status = 'overdue' if ts['status'] == 'overdue' else 'upcoming'
                    log_time = None

                schedule_status.append({
                    'medicine_name': med.name,
                    'scheduled_time': (
                        sched.scheduled_time.strftime('%I:%M %p').lstrip('0')
                        if sched.scheduled_time else None
                    ),
                    'window_label': sched.time_of_day or '',
                    'status': status,
                    'log_time': log_time,
                    'required_today': True,
                })

        state['expected_today'] = expected_today
        state['schedule_status_today'] = schedule_status

        # 7-day adherence rate (reuse existing utility)
        adherence = calculate_medicine_adherence_rate(user, days=7)
        if adherence is not None:
            state['adherence_7d'] = adherence

    except Exception:
        logger.warning("Medicine state build failed", exc_info=True)

    # ── Rich State Contract ──
    _overdue_meds = [
        s for s in state.get('schedule_status_today', [])
        if s.get('status') == 'overdue'
    ]
    _missed_meds = [
        s for s in state.get('schedule_status_today', [])
        if s.get('status') == 'missed'
    ]
    state['_contract'] = {
        'summary': {
            'active_count': state.get('active_count', 0),
            'active_medicines': state.get('active_medicines', []),
            'adherence_7d': state.get('adherence_7d'),
            'expected_today': state.get('expected_today', 0),
            'today_taken': state.get('today_taken', 0),
        },
        'today': {
            'schedule_status': state.get('schedule_status_today', []),
            'taken': state.get('today_taken', 0),
            'missed': state.get('today_missed', 0),
            'pending': state.get('today_pending', 0),
        },
        'upcoming': {},  # medicine has no future-looking data yet
        'alerts': {
            'overdue': _overdue_meds,
            'missed': _missed_meds,
            'needs_refill': state.get('needs_refill', []),
        },
    }
    state['_meta'] = _build_state_meta(
        completeness='full',
        confidence='high',
    )
    return state


# ── Calendar State ────────────────────────────────────────────────

def build_calendar_state(user):
    """
    Build calendar state from CalendarEvent records.

    Returns dict with flat keys (operational interface) + _contract overlay.
    See docs/SAE_STATE_CONTRACT.md for mapping table and migration plan.

    Contract sections: summary, today, upcoming, alerts
    For new consumers, prefer reading _contract over flat keys.
    """
    import datetime as _dt

    state = {}

    try:
        from apps.calendar_engine.models import CalendarEvent
        from apps.core.utils import get_user_now

        user_now = get_user_now(user)
        tz = user_now.tzinfo
        today_start = user_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = user_now.replace(hour=23, minute=59, second=59, microsecond=0)

        # Today's events (materialized rows only — no recurrence expansion)
        today_events = list(
            CalendarEvent.objects.filter(
                user=user,
                start_dt__lte=today_end,
                end_dt__gte=today_start,
                status__in=['scheduled', 'completed'],
                deleted_at__isnull=True,
            ).select_related('domain').order_by('start_dt')[:15]
        )

        state['today_event_count'] = len(today_events)

        # Serialize today's events with time status
        serialized = []
        current_event = None
        next_event = None
        overdue_events = []

        for ev in today_events:
            local_start = ev.start_dt.astimezone(tz)
            local_end = ev.end_dt.astimezone(tz)

            # Compute time status
            if ev.status == 'completed':
                time_status = 'completed'
            elif ev.end_dt <= user_now:
                time_status = 'past'
            elif ev.start_dt <= user_now <= ev.end_dt:
                time_status = 'in_progress'
            elif ev.start_dt <= user_now + _dt.timedelta(hours=1):
                time_status = 'upcoming_soon'
            else:
                time_status = 'upcoming'

            is_overdue = (
                ev.end_dt <= user_now and ev.status != 'completed'
            )

            entry = {
                'id': ev.id,
                'title': ev.title,
                'start': local_start.strftime('%I:%M %p').lstrip('0'),
                'end': local_end.strftime('%I:%M %p').lstrip('0'),
                'domain': ev.domain.name if ev.domain else '',
                'is_protected': ev.is_protected,
                'commitment_level': ev.commitment_level,
                'time_status': time_status,
                'is_overdue': is_overdue,
                'actual_status': ev.status,
            }
            serialized.append(entry)

            if is_overdue:
                overdue_events.append(entry)
            if time_status == 'in_progress' and current_event is None:
                current_event = entry
            if time_status in ('upcoming', 'upcoming_soon') and next_event is None:
                next_event = entry

        state['today_events'] = serialized
        state['current_event'] = current_event
        state['next_event'] = next_event
        state['overdue_events'] = overdue_events

        # Schedule density: total scheduled minutes today
        total_minutes = 0
        for ev in today_events:
            dur = (ev.end_dt - ev.start_dt).total_seconds() / 60
            if dur > 0:
                total_minutes += dur
        waking_minutes = 16 * 60  # 16 waking hours
        state['schedule_density'] = round(
            min(total_minutes / waking_minutes * 100, 100), 1
        ) if waking_minutes > 0 else 0

        # Upcoming events (next 3 days, excluding today)
        upcoming_start = today_end + _dt.timedelta(seconds=1)
        upcoming_end = today_start + _dt.timedelta(days=4)
        upcoming_qs = CalendarEvent.objects.filter(
            user=user,
            start_dt__gte=upcoming_start,
            start_dt__lte=upcoming_end,
            status='scheduled',
            deleted_at__isnull=True,
        ).select_related('domain').order_by('start_dt')[:10]

        state['upcoming_events'] = [
            {
                'title': ev.title,
                'start': ev.start_dt.astimezone(tz).strftime('%a %I:%M %p').lstrip('0'),
                'domain': ev.domain.name if ev.domain else '',
                'is_protected': ev.is_protected,
            }
            for ev in upcoming_qs
        ]

        # Conflict detection (overlapping events)
        conflicts = []
        for i, ev_a in enumerate(today_events):
            for ev_b in today_events[i + 1:]:
                if ev_a.end_dt > ev_b.start_dt and ev_a.start_dt < ev_b.end_dt:
                    if ev_a.status != 'completed' and ev_b.status != 'completed':
                        conflicts.append({
                            'event_a': ev_a.title,
                            'event_b': ev_b.title,
                        })
        if conflicts:
            state['schedule_conflicts'] = conflicts[:5]

    except ImportError:
        pass  # calendar_engine may not be deployed
    except Exception:
        logger.warning("Calendar state build failed", exc_info=True)

    # ── Rich State Contract ──
    state['_contract'] = {
        'summary': {
            'today_count': state.get('today_event_count', 0),
            'schedule_density': state.get('schedule_density', 0),
        },
        'today': {
            'items': state.get('today_events', []),
            'current_event': state.get('current_event'),
            'next_event': state.get('next_event'),
        },
        'upcoming': {
            'events': state.get('upcoming_events', []),
        },
        'alerts': {
            'overdue': state.get('overdue_events', []),
            'conflicts': state.get('schedule_conflicts', []),
        },
    }
    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('today_event_count', 0) > 0 or state.get('upcoming_events') else 'limited',
        confidence='high',
    )
    return state


# ── Routine State ─────────────────────────────────────────────────

def build_routine_state(user):
    """
    Build routine state from Routine, RoutineSchedule, RoutineLog models.

    CANON DECISION (2026-03-18):
        Routines are a FIRST-CLASS domain. The canonical source is the
        dedicated Routine/RoutineSchedule/RoutineLog model hierarchy in
        apps.life.models, NOT the Task.is_routine flag.

        Task.is_routine is a LEGACY compatibility layer for tasks that
        behave like daily routines. It is NOT the primary routine system
        and must NOT be mixed into this state builder.

        Future migration: Task.is_routine tasks should be migrated to
        RoutineSchedule entries. Until then, they remain in task state.

    Uses internal helper from apps.life.services._routine_internal for
    canonical window grouping and item collection (single source of truth).

    Returns:
        dict with today's routine items grouped by time window,
        completion status, and next pending item.
    """
    state = {}

    try:
        from apps.life.services._routine_internal import get_todays_routine_items

        result = get_todays_routine_items(user)

        state['total_routines'] = result['total_routines']
        if state['total_routines'] == 0:
            return state

        state['today_item_count'] = result['today_count']
        state['today_completed'] = result['today_completed']
        state['today_missed'] = result['today_missed']
        state['routine_items_today'] = result['items_by_window']
        state['current_window'] = result['current_window']
        state['routine_completion'] = result.get('routine_completion', {})

        # Find next pending item for CoS
        next_pending = None
        for window_items in result['items_by_window'].values():
            for item in window_items:
                if item.get('status') == 'pending' and next_pending is None:
                    next_pending = item
                    break
            if next_pending:
                break
        state['next_pending_item'] = next_pending

    except ImportError:
        pass  # Routine models may not exist
    except Exception:
        logger.warning("Routine state build failed", exc_info=True)

    # ── Rich State Contract ──
    _missed_items = []
    for window_items in state.get('routine_items_today', {}).values():
        _missed_items.extend(
            [i for i in window_items if i.get('status') == 'missed']
        )
    state['_contract'] = {
        'summary': {
            'total_routines': state.get('total_routines', 0),
            'today_count': state.get('today_item_count', 0),
            'today_completed': state.get('today_completed', 0),
            'today_missed': state.get('today_missed', 0),
        },
        'today': {
            'items_by_window': state.get('routine_items_today', {}),
            'current_window': state.get('current_window'),
            'next_up': state.get('next_pending_item'),
            'routine_completion': state.get('routine_completion', {}),
        },
        'upcoming': {},  # routines are daily — no future items
        'alerts': {
            'missed': _missed_items,
        },
    }
    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('total_routines', 0) > 0 else 'limited',
        confidence='high',
    )
    return state


# ── Daily Execution Status (Canonical Truth) ────────────────────


def build_daily_execution_status(user):
    """
    Canonical boolean execution truth for today — per domain.

    This is the SINGLE SOURCE OF TRUTH for whether a user has completed
    specific activities today. Beth must NEVER infer completion from
    streaks, aggregates, or patterns — only from this explicit state.

    Returns dict with explicit booleans for each domain.
    """
    from apps.core.utils import get_user_today
    user_today = get_user_today(user)
    state = {}

    try:
        # Tasks: count of tasks completed today
        from apps.life.models import Task
        completed_tasks = Task.objects.filter(
            user=user, completion_status='completed',
            completed_at__date=user_today,
        )
        state['tasks_completed_today'] = completed_tasks.count()
        state['completed_task_ids'] = list(
            completed_tasks.values_list('id', flat=True)[:50]
        )
    except Exception:
        state['tasks_completed_today'] = 0
        state['completed_task_ids'] = []

    try:
        # Routines: IDs of completed routine items today
        from apps.life.models import RoutineLog
        state['completed_routine_item_ids'] = list(
            RoutineLog.objects.filter(
                schedule__routine__user=user,
                scheduled_date=user_today,
                log_status__in=('completed', 'completed_late'),
            ).values_list('schedule_id', flat=True)[:50]
        )
    except Exception:
        state['completed_routine_item_ids'] = []

    try:
        # Journal: explicit entry today
        from apps.journal.models import JournalEntry
        state['journal_completed'] = JournalEntry.objects.filter(
            user=user, entry_date=user_today,
        ).exists()
    except Exception:
        state['journal_completed'] = False

    try:
        # Workout: explicit session today
        from apps.health.models import WorkoutSession
        state['workout_completed'] = WorkoutSession.objects.filter(
            user=user, date=user_today,
        ).exclude(status='deleted').exists()
    except Exception:
        state['workout_completed'] = False

    try:
        # Faith: use Execution Truth Engine (includes routine→faith bridge)
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, user_today)
        faith = truth['domains']['faith']
        state['bible_reading_completed'] = faith['bible_reading_completed']
        state['prayer_completed'] = faith['prayer_completed']
        state['faith_engaged'] = faith['prayer_completed'] or faith['bible_reading_completed']
    except Exception:
        state['bible_reading_completed'] = False
        state['prayer_completed'] = False
        state['faith_engaged'] = False

    return state


# ── Builder Registry ─────────────────────────────────────────────

# Maps module names to their builder functions.
# New modules can be registered by adding to this dict.
def build_behavior_state(user):
    """
    Build behavior score state from cross-domain adherence outputs.

    Returns composite score + per-domain breakdown for CoS consumption.
    """
    state = {}
    try:
        from apps.core.behavior.behavior_score_engine import compute_behavior_score_7d
        result = compute_behavior_score_7d(user)
        state['behavior_score'] = result.get('score')
        state['behavior_strongest'] = result.get('strongest_domain')
        state['behavior_weakest'] = result.get('weakest_domain')
        state['behavior_domains_missing'] = result.get('domains_missing', [])
        # Per-domain adherence summaries
        for d in result.get('domains', []):
            key = f"behavior_{d['domain']}"
            state[key] = {
                'adherence': d['adherence'],
                'on_time_rate': d['on_time_rate'],
                'expected': d['expected'],
                'completed': d['completed'],
                'late': d['late'],
                'skipped': d['skipped'],
                'missed': d['missed'],
            }
    except Exception as e:
        logger.warning("build_behavior_state failed: %s", e, exc_info=True)
        state['behavior_score'] = None
    return state


# ── Phase 2 Domain Builders ──────────────────────────────────────
# New domains designed with _contract as primary structure.
# See docs/SAE_STATE_CONTRACT.md for architecture.


def build_finance_state(user):
    """Build finance state: obligations, cash pressure, spending.

    _contract is primary. Flat keys minimal.
    See docs/SAE_STATE_CONTRACT.md.
    """
    state = {}
    try:
        from apps.core.utils import get_user_today
        from apps.finance.models import (
            Budget, FinancialAccount, FinancialGoal,
            FinancialMetricSnapshot, RecurringTransaction, Transaction,
        )
        from django.db.models import Sum

        user_today = get_user_today(user)
        first_of_month = user_today.replace(day=1)

        # Accounts
        accounts = FinancialAccount.objects.filter(
            user=user, status='active', is_hidden=False,
        )
        assets = sum(float(a.current_balance) for a in accounts if a.is_asset)
        liabilities = sum(abs(float(a.current_balance)) for a in accounts if a.is_liability)
        net_worth = assets - liabilities

        account_list = [
            {'name': a.name, 'type': a.account_type, 'balance': float(a.current_balance)}
            for a in accounts[:15]
        ]

        # Active goals
        goals = FinancialGoal.objects.filter(
            user=user, goal_status='active',
        ).order_by('target_date')[:10]
        goal_list = [
            {
                'name': g.name, 'type': g.goal_type,
                'progress_pct': round(g.progress_percentage, 1),
                'target': float(g.target_amount or 0),
                'current': float(g.current_amount or 0),
                'target_date': g.target_date.isoformat() if g.target_date else None,
            }
            for g in goals
        ]

        # Budgets this month
        budgets = Budget.objects.filter(
            user=user, month=first_of_month,
        ).select_related('category')[:15]
        over_budget = [
            {
                'category': b.category.name if b.category else 'Uncategorized',
                'budgeted': float(b.budgeted_amount or 0),
                'spent': float(b.spent_amount or 0),
                'pct': round(b.spent_percentage, 1),
            }
            for b in budgets if b.spent_percentage > 100
        ]
        warning_budget = [
            {
                'category': b.category.name if b.category else 'Uncategorized',
                'pct': round(b.spent_percentage, 1),
            }
            for b in budgets if 80 <= b.spent_percentage <= 100
        ]

        # Recurring obligations
        active_recurring = RecurringTransaction.objects.filter(
            user=user, is_active=True, transaction_type='expense',
        )
        overdue_recurring = [
            {'name': r.name, 'amount': float(r.amount), 'due': r.next_due_date.isoformat()}
            for r in active_recurring
            if r.next_due_date and r.next_due_date < user_today
        ][:10]
        upcoming_recurring = [
            {'name': r.name, 'amount': float(r.amount), 'due': r.next_due_date.isoformat()}
            for r in active_recurring
            if r.next_due_date and user_today <= r.next_due_date <= user_today + timedelta(days=14)
        ][:10]

        # Spending this month
        month_spending = Transaction.objects.filter(
            user=user, date__gte=first_of_month, amount__lt=0,
        ).aggregate(total=Sum('amount'))['total'] or 0
        month_income = Transaction.objects.filter(
            user=user, date__gte=first_of_month, amount__gt=0,
        ).exclude(
            is_opening_balance=True,
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Cash pressure: simple heuristic
        if liabilities > assets * 0.8:
            pressure = 'high'
        elif over_budget:
            pressure = 'medium'
        else:
            pressure = 'low'

        state['_contract'] = {
            'summary': {
                'account_count': accounts.count(),
                'net_worth': round(net_worth, 2),
                'total_assets': round(assets, 2),
                'total_liabilities': round(liabilities, 2),
                'active_goal_count': len(goal_list),
                'month_spending': round(abs(float(month_spending)), 2),
                'month_income': round(float(month_income), 2),
                'cash_pressure_level': pressure,
            },
            'today': {},
            'upcoming': {
                'recurring_due_14d': upcoming_recurring,
                'goals': goal_list,
            },
            'alerts': {
                'overdue_bills': overdue_recurring,
                'over_budget': over_budget,
                'budget_warnings': warning_budget,
            },
            'detail': {
                'accounts': account_list,
            },
        }
        # Minimal flat keys for backward compat with existing CoS builder
        state['finance_goals'] = goal_list
        state['finance_budgets_alert'] = over_budget

    except ImportError:
        pass
    except Exception:
        logger.warning("Finance state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('_contract', {}).get('summary', {}).get('account_count', 0) > 0 else 'limited',
        confidence='high',
    )
    return state


def build_relationships_state(user):
    """Build relationships state: connection health, neglect detection.

    Uses canonical Person model (apps.relationships). Falls back to legacy
    model (apps.core.ai_relationships) for importance_tier/cadence_target
    if available.

    _contract is primary. See docs/SAE_STATE_CONTRACT.md.
    """
    state = {}
    try:
        from apps.core.utils import get_user_today

        user_today = get_user_today(user)
        people = []
        neglected = []

        # Try canonical model first
        try:
            from apps.relationships.models import Person, RelationshipInteraction
            contacts = Person.objects.filter(
                owner=user, deleted_at__isnull=True,
            ).order_by('-interaction_count')[:25]

            for p in contacts:
                days_since = None
                if p.last_interaction_date:
                    days_since = (user_today - p.last_interaction_date).days

                entry = {
                    'name': p.get_display_name(),
                    'relationship_type': p.relationship_type or '',
                    'days_since_contact': days_since,
                    'interaction_count': p.interaction_count or 0,
                }
                people.append(entry)

                # Neglect detection: >30 days with no contact for active relationships
                if days_since is not None and days_since > 30:
                    neglected.append(entry)
                elif days_since is None and p.interaction_count == 0:
                    neglected.append(entry)  # Never contacted

        except ImportError:
            # Fall back to legacy model
            from apps.core.ai_relationships.models import Relationship
            rels = Relationship.objects.filter(
                user=user, person__is_active=True,
            ).select_related('person').order_by('importance_tier')[:25]

            for rel in rels:
                days_since = None
                if rel.last_interaction:
                    days_since = (user_today - rel.last_interaction).days

                entry = {
                    'name': rel.person.display_name,
                    'tier': rel.importance_tier,
                    'cadence_target': rel.cadence_target,
                    'days_since_contact': days_since,
                }
                people.append(entry)

                # Neglect: compare to cadence target
                _cadence_days = {
                    'daily': 2, 'weekly': 10, 'biweekly': 21,
                    'monthly': 45, 'quarterly': 120,
                }
                threshold = _cadence_days.get(rel.cadence_target, 45)
                if days_since is not None and days_since > threshold:
                    neglected.append(entry)

        # Birthdays (from life.SignificantEvent or similar — check what exists)
        birthdays_today = []
        upcoming_birthdays = []
        try:
            from apps.life.models import SignificantEvent
            bday_events = SignificantEvent.objects.filter(
                user=user, event_type='birthday',
            )
            for ev in bday_events:
                if ev.next_occurrence:
                    days_until = (ev.next_occurrence - user_today).days
                    entry = {'name': ev.title, 'date': ev.next_occurrence.isoformat()}
                    if days_until == 0:
                        birthdays_today.append(entry)
                    elif 0 < days_until <= 14:
                        upcoming_birthdays.append(entry)
        except (ImportError, Exception):
            pass

        state['_contract'] = {
            'summary': {
                'active_count': len(people),
                'neglected_count': len(neglected),
            },
            'today': {
                'birthdays': birthdays_today,
            },
            'upcoming': {
                'birthdays': upcoming_birthdays[:5],
            },
            'alerts': {
                'neglected': neglected[:10],
            },
            'detail': {
                'people': people,
            },
        }
        # Flat keys for backward compat with existing CoS builder
        state['relationship_signals'] = people[:10]

    except ImportError:
        pass
    except Exception:
        logger.warning("Relationships state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('_contract', {}).get('summary', {}).get('active_count', 0) > 0 else 'limited',
        confidence='medium',  # interaction data may be incomplete
    )
    return state


def build_brain_training_state(user):
    """Build brain training state: consistency, performance, streaks.

    _contract is primary. See docs/SAE_STATE_CONTRACT.md.
    """
    state = {}
    try:
        from apps.brain_training.models import (
            DailyStats, GameSession, UserGameStats, UserOverallStats,
        )
        from apps.core.utils import get_user_today

        user_today = get_user_today(user)
        week_ago = user_today - timedelta(days=7)

        # Overall stats
        overall = UserOverallStats.objects.filter(user=user).first()

        # Recent daily stats
        recent_days = DailyStats.objects.filter(
            user=user, date__gte=week_ago,
        ).order_by('-date')[:7]
        sessions_this_week = sum(d.sessions_completed for d in recent_days)
        total_score_week = sum(d.total_score for d in recent_days)
        avg_score_week = (
            round(total_score_week / sessions_this_week)
            if sessions_this_week > 0 else None
        )

        # Today's sessions
        today_stats = DailyStats.objects.filter(
            user=user, date=user_today,
        ).first()
        completed_today = today_stats.sessions_completed if today_stats else 0

        # Performance trend (compare last 7d vs prior 7d)
        prior_week_start = user_today - timedelta(days=14)
        prior_days = DailyStats.objects.filter(
            user=user, date__gte=prior_week_start, date__lt=week_ago,
        )
        prior_sessions = sum(d.sessions_completed for d in prior_days)
        prior_score = sum(d.total_score for d in prior_days)
        prior_avg = round(prior_score / prior_sessions) if prior_sessions > 0 else None

        if avg_score_week and prior_avg:
            if avg_score_week > prior_avg + 5:
                trend = 'improving'
            elif avg_score_week < prior_avg - 5:
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'

        # Streak risk
        streak = overall.current_streak if overall else 0
        last_played = overall.last_played_date if overall else None
        streak_at_risk = False
        if last_played and (user_today - last_played).days >= 1:
            streak_at_risk = True

        daily_history = [
            {
                'date': d.date.isoformat(),
                'sessions': d.sessions_completed,
                'best_score': d.best_score,
            }
            for d in recent_days
        ]

        state['_contract'] = {
            'summary': {
                'sessions_this_week': sessions_this_week,
                'streak_length': streak,
                'avg_score_7d': avg_score_week,
                'performance_trend': trend,
                'total_sessions': overall.total_sessions if overall else 0,
                'total_completed': overall.total_completed if overall else 0,
            },
            'today': {
                'completed': completed_today,
            },
            'upcoming': {},
            'alerts': {
                'streak_at_risk': streak_at_risk,
                'declining_performance': trend == 'declining',
            },
            'detail': {
                'daily_history': daily_history,
                'favorite_game': (
                    overall.favorite_game.name if overall and overall.favorite_game else None
                ),
            },
        }
        # Flat keys for backward compat with existing CoS builder
        state['brain_training'] = {
            'total_sessions': overall.total_sessions if overall else 0,
            'total_completed': overall.total_completed if overall else 0,
            'current_streak': streak,
            'favorite_game': (
                overall.favorite_game.name if overall and overall.favorite_game else None
            ),
        }

    except ImportError:
        pass
    except Exception:
        logger.warning("Brain training state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('_contract', {}).get('summary', {}).get('total_sessions', 0) > 0 else 'limited',
        confidence='high',
    )
    return state


def build_medical_state(user):
    """Build medical state: lab results, abnormal flags, providers.

    _contract is primary. See docs/SAE_STATE_CONTRACT.md.
    Note: No appointment model exists — completeness is 'partial'.
    """
    state = {}
    try:
        from apps.medical.models import LabPanel, LabResult

        # Recent abnormal results (90 days)
        cutoff = get_current_time() - timedelta(days=90)
        abnormal = list(LabResult.objects.filter(
            user=user,
            collected_at__gte=cutoff,
            abnormal_flag__in=['L', 'H', 'LL', 'HH', 'A'],
        ).select_related('canonical_test').order_by('-collected_at')[:10])

        abnormal_list = [
            {
                'test': r.canonical_test.short_name if r.canonical_test else r.raw_test_name[:30],
                'value': str(r.value_text)[:20],
                'flag': r.abnormal_flag,
                'date': r.collected_at.strftime('%Y-%m-%d') if r.collected_at else None,
            }
            for r in abnormal
        ]

        # Recent panels
        panels = list(LabPanel.objects.filter(
            user=user, collected_at__gte=cutoff,
        ).order_by('-collected_at')[:5])
        panel_list = [
            {
                'type': p.panel_type, 'name': p.name[:40] if p.name else p.panel_type,
                'date': p.collected_at.strftime('%Y-%m-%d') if p.collected_at else None,
                'result_count': p.result_count, 'abnormal_count': p.abnormal_count,
            }
            for p in panels
        ]

        # Total result count for completeness
        total_results = LabResult.objects.filter(user=user).count()

        # Provider count
        provider_count = 0
        try:
            from apps.health.models import MedicalProvider
            provider_count = MedicalProvider.objects.filter(user=user).count()
        except ImportError:
            pass

        state['_contract'] = {
            'summary': {
                'total_lab_results': total_results,
                'recent_abnormal_count': len(abnormal_list),
                'recent_panel_count': len(panel_list),
                'provider_count': provider_count,
            },
            'today': {},  # No appointment model
            'upcoming': {},  # No appointment model
            'alerts': {
                'abnormal_results': abnormal_list,
            },
            'detail': {
                'recent_panels': panel_list,
            },
        }
        # Flat keys for backward compat with existing CoS builder
        state['medical_alerts'] = abnormal_list
        state['recent_lab_panels'] = panel_list

    except ImportError:
        pass
    except Exception:
        logger.warning("Medical state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='partial',  # No appointment tracking model
        confidence='high',
    )
    return state


def build_capture_state(user):
    """Build capture state: intake pressure, backlog, processing status.

    _contract is primary. See docs/SAE_STATE_CONTRACT.md.
    """
    state = {}
    try:
        from apps.capture.models import CaptureEntry, PendingCapture
        from apps.core.utils import get_user_today

        user_today = get_user_today(user)
        week_ago = user_today - timedelta(days=7)

        # Pending uploads
        pending_count = PendingCapture.objects.filter(
            user=user, status__in=['pending', 'uploading'],
        ).count()

        # Recent captures by status
        recent_ready = list(CaptureEntry.objects.filter(
            user=user, status='ready',
            created_at__date__gte=week_ago,
        ).order_by('-created_at')[:10])

        failed_count = CaptureEntry.objects.filter(
            user=user, status='failed',
            created_at__date__gte=week_ago,
        ).count()

        # Today's captures
        today_count = CaptureEntry.objects.filter(
            user=user, created_at__date=user_today,
        ).count()

        # Volume 7d
        volume_7d = CaptureEntry.objects.filter(
            user=user, created_at__date__gte=week_ago,
        ).count()

        # Stale items (ready but old — not reviewed)
        stale_cutoff = get_current_time() - timedelta(days=14)
        stale_count = CaptureEntry.objects.filter(
            user=user, status='ready',
            created_at__lt=stale_cutoff,
        ).count()

        # Backlog level
        total_unprocessed = pending_count + len(recent_ready) + failed_count
        if total_unprocessed > 10:
            backlog_level = 'high'
        elif total_unprocessed > 3:
            backlog_level = 'medium'
        else:
            backlog_level = 'low'

        capture_items = [
            {
                'title': e.title[:60] if e.title else 'Untitled',
                'category': e.category,
                'subcategory': e.subcategory,
                'date': e.created_at.strftime('%Y-%m-%d'),
            }
            for e in recent_ready
        ]

        state['_contract'] = {
            'summary': {
                'unprocessed_count': total_unprocessed,
                'backlog_level': backlog_level,
                'capture_volume_7d': volume_7d,
            },
            'today': {
                'captures_today': today_count,
            },
            'upcoming': {},
            'alerts': {
                'pending_uploads': pending_count,
                'failed_count': failed_count,
                'stale_items': stale_count,
            },
            'detail': {
                'recent_captures': capture_items,
            },
        }
        # Flat keys for backward compat
        state['capture_status'] = {
            'pending_uploads': pending_count,
            'recent_captures': capture_items,
        }

    except ImportError:
        pass
    except Exception:
        logger.warning("Capture state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='full',
        confidence='high',
    )
    return state


def build_sports_state(user):
    """Build sports state: followed teams, game awareness, urgency signals.

    Reads from cache first. On cache miss, falls back to a lightweight
    bounded query (user's followed teams + their next/last games only).
    This fallback is safe for request path — single user, indexed queries.

    If sports module is disabled, returns empty state immediately.

    _contract is primary. See docs/SAE_STATE_CONTRACT.md.
    """
    state = {}
    try:
        prefs = getattr(user, 'preferences', None)
        if not prefs or not prefs.sports_enabled:
            state['enabled'] = False
            state['_meta'] = _build_state_meta(
                completeness='full',
                confidence='high',
            )
            return state

        state['enabled'] = True

        # Try cache first
        from apps.sports.services.cache_manager import (
            get_user_sports_summary,
            get_user_today_games,
        )

        summaries = get_user_sports_summary(user)
        today_games = get_user_today_games(user)

        if summaries:
            state['teams_followed'] = len(summaries)
            state['games_today'] = len(today_games)
            state['today_games'] = today_games
            all_signals = set()
            for s in summaries:
                all_signals.update(s.get('active_signals', []))
            state['active_signals'] = sorted(all_signals)
            state['team_summaries'] = summaries
        else:
            # Cache empty — build from DB (lightweight, bounded to user's teams)
            _build_sports_state_from_db(user, state)

    except ImportError:
        logger.debug("Sports module not installed")
    except Exception:
        logger.warning("Sports state build failed", exc_info=True)

    state['_meta'] = _build_state_meta(
        completeness='full' if state.get('team_summaries') else 'partial',
        confidence='high',
    )
    return state


def _build_sports_state_from_db(user, state):
    """Fallback: build sports state directly from DB when cache is empty.

    Lightweight query: only user's followed teams + their next/last games.
    Bounded by user's team count (typically 5-15 teams).
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.sports.models import GameEvent, UserTeamFollow

    now = timezone.now()

    follows = (
        UserTeamFollow.objects.filter(user=user, is_active=True)
        .select_related("team__league")
    )
    if not follows.exists():
        state['teams_followed'] = 0
        state['team_summaries'] = []
        return

    team_ids = [f.team_id for f in follows]
    follow_map = {f.team_id: f for f in follows}

    # Next upcoming game per team
    upcoming = (
        GameEvent.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
            start_time__gte=now,
            status__in=[GameEvent.STATUS_SCHEDULED, GameEvent.STATUS_LIVE],
        )
        .select_related("home_team", "away_team")
        .order_by("start_time")
    )
    next_game_map = {}
    for game in upcoming:
        for tid in [game.home_team_id, game.away_team_id]:
            if tid in team_ids and tid not in next_game_map:
                next_game_map[tid] = game

    # Last completed game per team
    recent = (
        GameEvent.objects.filter(
            Q(home_team_id__in=team_ids) | Q(away_team_id__in=team_ids),
            status=GameEvent.STATUS_FINAL,
        )
        .select_related("home_team", "away_team")
        .order_by("-start_time")
    )
    last_game_map = {}
    for game in recent:
        for tid in [game.home_team_id, game.away_team_id]:
            if tid in team_ids and tid not in last_game_map:
                last_game_map[tid] = game

    summaries = []
    today_games = []
    active_signals = set()

    for follow in follows:
        team = follow.team
        next_game = next_game_map.get(team.id)
        last_game = last_game_map.get(team.id)

        # Determine urgency
        status = "upcoming"
        if next_game:
            if next_game.status == GameEvent.STATUS_LIVE:
                status = "live"
                active_signals.add("game_live")
            elif next_game.start_time <= now + timedelta(hours=1):
                status = "starting_soon"
                active_signals.add("game_starting_soon")
            elif next_game.start_time.date() == now.date():
                status = "today"
                active_signals.add("game_today")

        summary = {
            "team_id": team.id,
            "team_name": str(team),
            "league": team.league.abbreviation,
            "priority": follow.priority,
            "status": status,
            "next_game": None,
            "last_result": None,
            "active_signals": [],
        }

        if next_game:
            opponent = next_game.get_opponent(team)
            summary["next_game"] = {
                "opponent": str(opponent) if opponent else "TBD",
                "time": next_game.start_time.strftime("%-I:%M %p"),
                "venue": next_game.venue,
            }
            if next_game.is_live:
                summary["next_game"]["score"] = next_game.get_score_display()
            summary["active_signals"].append(f"game_{status}" if status != "upcoming" else "")

            if status in ("today", "starting_soon", "live"):
                today_games.append({
                    "team": str(team),
                    "opponent": str(opponent) if opponent else "TBD",
                    "time": next_game.start_time.strftime("%-I:%M %p"),
                    "status": status,
                })

        if last_game:
            opponent = last_game.get_opponent(team)
            if last_game.user_team_won(team):
                result = "W"
                active_signals.add("team_win")
            elif last_game.user_team_lost(team):
                result = "L"
                active_signals.add("team_loss")
            else:
                result = "T"
            summary["last_result"] = {
                "opponent": str(opponent) if opponent else "TBD",
                "result": result,
                "score": last_game.get_score_display(),
            }

        # Clean empty signal entries
        summary["active_signals"] = [s for s in summary["active_signals"] if s]

        summaries.append(summary)

    summaries.sort(key=lambda x: x["priority"])

    state['teams_followed'] = len(summaries)
    state['games_today'] = len(today_games)
    state['today_games'] = today_games
    state['active_signals'] = sorted(active_signals)
    state['team_summaries'] = summaries


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
    "medicine": build_medicine_state,
    "behavior": build_behavior_state,
    "calendar": build_calendar_state,
    "routine": build_routine_state,
    "finance": build_finance_state,
    "relationships": build_relationships_state,
    "brain_training": build_brain_training_state,
    "medical": build_medical_state,
    "capture": build_capture_state,
    "sports": build_sports_state,
    # NOTE: daily_execution_status is DEPRECATED — subsumed by the 'execution'
    # module which provides identical domain booleans in summaries.domains.
    # Kept as function only for backward compat; NOT registered in MODULE_BUILDERS.
}


def _build_execution_state(user):
    """SAE wrapper for the authoritative execution contract."""
    try:
        from apps.core.execution.today_execution import build_today_execution
        return build_today_execution(user)
    except Exception:
        logger.warning("Execution contract build failed", exc_info=True)
        return {'items': [], 'summaries': {}}


# Register execution after function definition (forward reference workaround)
MODULE_BUILDERS["execution"] = _build_execution_state


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
