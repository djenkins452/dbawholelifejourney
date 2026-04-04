"""
COS-CX5: Diagnostic Context Expansion
======================================

When user asks WHY questions ("why am I struggling", "why can't I stick
to workouts", "what's going wrong"), inject cross-domain causal signals
so the LLM can reason through the chain:

  sleep deficit → skipped workout → mood drop → missed tasks

This is NOT a new engine — it's a response-mode context expander that
gathers existing SAE data across domains and presents it in a format
optimized for causal reasoning.

Performance target: < 8ms (bounded queries across domains).
Token budget: ~200 tokens max.
"""
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


# Trigger phrases that activate diagnostic mode
DIAGNOSTIC_TRIGGERS = [
    'why am i', 'why can\'t i', 'why do i', 'why don\'t i',
    'what\'s going wrong', 'what am i doing wrong', 'what\'s wrong',
    'struggling with', 'can\'t seem to', 'keep failing',
    'not working', 'falling behind', 'losing motivation',
    'what happened', 'why did i', 'diagnose', 'root cause',
    'what\'s causing', 'help me understand why',
]


def is_diagnostic_query(message):
    """
    Check if user message is a diagnostic/why question.

    Args:
        message: str — user's message

    Returns:
        bool
    """
    msg_lower = message.lower().strip()
    return any(trigger in msg_lower for trigger in DIAGNOSTIC_TRIGGERS)


def build_diagnostic_context(user, now, message=""):
    """
    Build cross-domain diagnostic signals for causal reasoning.

    Gathers recent data across sleep, exercise, mood, tasks, medication,
    and journal to enable the LLM to trace causal chains.

    Args:
        user: Django User object
        now: timezone-aware datetime in user's timezone
        message: user's message (for topic detection)

    Returns:
        str — formatted diagnostic block, or "" if insufficient data.
    """
    try:
        today = now.date()
        week_ago = today - timedelta(days=7)
        two_weeks_ago = today - timedelta(days=14)

        signals = {}

        # --- Sleep ---
        signals['sleep'] = _get_sleep_signals(user, week_ago, today)

        # --- Exercise ---
        signals['exercise'] = _get_exercise_signals(user, week_ago, two_weeks_ago, today)

        # --- Mood / Journal ---
        signals['mood'] = _get_mood_signals(user, week_ago, today)

        # --- Task completion ---
        signals['tasks'] = _get_task_signals(user, week_ago, today)

        # --- Medication adherence ---
        signals['medication'] = _get_medication_signals(user, week_ago, today)

        # --- Stress markers ---
        signals['stress'] = _get_stress_signals(user, week_ago, today)

        # Filter out empty signals
        active_signals = {k: v for k, v in signals.items() if v}

        if not active_signals:
            return ""

        lines = [
            "=== DIAGNOSTIC SIGNALS (7-day cross-domain) ===",
            "Use these signals to reason through causal chains. "
            "Connect the dots across domains — don't just list them.",
            "",
        ]

        for domain, data in active_signals.items():
            label = domain.replace('_', ' ').title()
            lines.append(f"{label}: {data}")

        # Add reasoning instruction
        lines.append("")
        lines.append(
            "REASONING TASK: Identify the most likely causal chain. "
            "For example: low sleep → skipped workouts → mood drop → missed tasks. "
            "Present your diagnosis conversationally, not as a data dump."
        )

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Diagnostic context skipped: %s", e)
        return ""


def _get_sleep_signals(user, week_ago, today):
    """Get sleep data for the past week."""
    try:
        from apps.health.models import SleepEntry

        entries = SleepEntry.objects.filter(
            user=user,
            sleep_date__gte=week_ago,
            sleep_date__lte=today,
        ).values_list('total_duration_minutes', flat=True)

        entries = list(entries)
        if not entries:
            return None

        # Convert minutes to hours for readability
        hours = [m / 60.0 for m in entries if m]
        if not hours:
            return None
        avg = sum(hours) / len(hours)
        low_days = sum(1 for h in hours if h < 6.5)

        status = "adequate" if avg >= 7 else ("low" if avg >= 6 else "very low")
        result = f"{avg:.1f}h avg ({status})"
        if low_days > 0:
            result += f", {low_days} days under 6.5h"
        return result
    except Exception:
        return None


def _get_exercise_signals(user, week_ago, two_weeks_ago, today):
    """Get exercise frequency and trend."""
    try:
        from apps.health.services.workout_queries import WorkoutQueries

        recent = WorkoutQueries.completed_in_range(
            user, week_ago, today,
        ).count()

        prior = WorkoutQueries.completed_in_range(
            user, two_weeks_ago, week_ago - timedelta(days=1),
        ).count()

        if recent == 0 and prior == 0:
            return None

        trend = "stable"
        if recent > prior + 1:
            trend = "increasing"
        elif recent < prior - 1:
            trend = "decreasing"

        freq = "none" if recent == 0 else f"{recent}x this week"
        return f"{freq} (prior week: {prior}x, trend: {trend})"
    except Exception:
        return None


def _get_mood_signals(user, week_ago, today):
    """Get mood trend from journal entries."""
    try:
        from apps.journal.models import JournalEntry

        entries = JournalEntry.objects.filter(
            user=user,
            created_at__date__gte=week_ago,
            created_at__date__lte=today,
        ).exclude(
            mood__isnull=True
        ).exclude(
            mood=''
        ).values_list('mood', flat=True)

        moods = list(entries)
        if not moods:
            # Check entry count even without mood
            count = JournalEntry.objects.filter(
                user=user,
                created_at__date__gte=week_ago,
                created_at__date__lte=today,
            ).count()
            if count == 0:
                return "no journal entries this week"
            return None

        # Count mood categories
        mood_counts = {}
        for m in moods:
            m_lower = m.lower()
            mood_counts[m_lower] = mood_counts.get(m_lower, 0) + 1

        top_moods = sorted(mood_counts.items(), key=lambda x: x[1], reverse=True)
        mood_str = ", ".join(f"{mood} ({count}x)" for mood, count in top_moods[:3])
        return mood_str
    except Exception:
        return None


def _get_task_signals(user, week_ago, today):
    """Get task completion rate."""
    try:
        from apps.life.models import Task

        completed = Task.objects.filter(
            user=user,
            completed_at__date__gte=week_ago,
            completed_at__date__lte=today,
        ).count()

        overdue = Task.objects.filter(
            user=user,
            completion_status='pending',
            due_date__lt=today,
        ).count()

        if completed == 0 and overdue == 0:
            return None

        result = f"{completed} completed this week"
        if overdue > 0:
            result += f", {overdue} currently overdue"
        return result
    except Exception:
        return None


def _get_medication_signals(user, week_ago, today):
    """Get medication adherence trend (schedule-based, not logs-only)."""
    try:
        from apps.health.medicine_utils import calculate_medicine_adherence

        adh = calculate_medicine_adherence(user, week_ago, today)
        if adh["expected_doses"] == 0:
            return None

        pct = adh["adherence_rate"] or 0
        taken = adh["taken_doses"]
        total = adh["expected_doses"]
        status = "good" if pct >= 90 else ("moderate" if pct >= 70 else "low")
        return f"{pct}% adherence ({taken}/{total} doses, {status})"
    except Exception:
        return None


def _get_stress_signals(user, week_ago, today):
    """Get stress indicators from heart rate data."""
    try:
        from apps.health.models import HeartRateEntry

        # Check for elevated resting heart rate
        hr_entries = list(
            HeartRateEntry.objects.filter(
                user=user,
                context='resting',
                recorded_at__date__gte=week_ago,
                recorded_at__date__lte=today,
            ).values_list('bpm', flat=True)[:20]
        )

        if hr_entries:
            avg_hr = sum(hr_entries) / len(hr_entries)
            if avg_hr > 85:
                return f"elevated resting HR ({avg_hr:.0f} bpm avg)"

        return None
    except Exception:
        return None
