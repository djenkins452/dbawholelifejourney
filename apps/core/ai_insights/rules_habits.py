"""
Habits Insight Rules — Broken streaks and consistency detection.
"""

from datetime import date, timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class HabitBrokenStreakRule(BaseInsightRule):
    rule_name = "habit_broken_streak"
    module = "purpose"
    insight_type = "habit_broken_streak"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.purpose.models import HabitEntry, HabitGoal

        active_habits = HabitGoal.objects.filter(
            user=user, status="active"
        )

        insights = []
        today = date.today()
        window_start, window_end = get_time_window(days=14)

        for habit in active_habits:
            # Get last 14 days of entries
            recent_entries = list(
                HabitEntry.objects.filter(
                    goal=habit,
                    date__gte=today - timedelta(days=14),
                    date__lte=today,
                    completed=True,
                )
                .order_by("date")
                .values_list("date", flat=True)
            )

            if len(recent_entries) < 3:
                continue

            # Check if there was a streak that's now broken
            latest_entry = recent_entries[-1] if recent_entries else None
            if not latest_entry:
                continue

            days_since_last = (today - latest_entry).days
            if days_since_last < 2:
                continue

            # Had a streak, now broken
            insights.append(
                {
                    "severity": "info",
                    "title": f'"{habit.name}" streak paused',
                    "message": (
                        f'You had a strong streak on "{habit.name}" but haven\'t '
                        f"logged it in {days_since_last} days. "
                        f"Every day is a fresh start!"
                    ),
                    "confidence_score": 0.75,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Habit '{habit.name}' had "
                        f"{len(recent_entries)} completions in 14 days but "
                        f"last log was {days_since_last} days ago (threshold: 2)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "habit_id": habit.id,
                        "habit_name": habit.name,
                        "completions_14d": len(recent_entries),
                        "days_since_last": days_since_last,
                        "last_date": str(latest_entry),
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type,
                        window_start.date(),
                        window_end.date(),
                        [habit.id],
                    ),
                }
            )

        return insights


@register
class HabitConsistencyPositiveRule(BaseInsightRule):
    rule_name = "habit_consistency_positive"
    module = "purpose"
    insight_type = "habit_consistency_positive"

    def applies(self, user, event):
        return event.get("module") == "purpose" and event.get("action") in (
            "log_habit",
            "scheduled_check",
        )

    def evaluate(self, user, event):
        from apps.purpose.models import HabitEntry, HabitGoal

        active_habits = HabitGoal.objects.filter(
            user=user, status="active"
        )

        insights = []
        today = date.today()
        window_start = today - timedelta(days=14)
        window_end_dt_start, window_end_dt = get_time_window(days=14)

        for habit in active_habits:
            completions = HabitEntry.objects.filter(
                goal=habit,
                date__gte=window_start,
                date__lte=today,
                completed=True,
            ).count()

            if completions < 5:
                continue

            insights.append(
                {
                    "severity": "positive",
                    "title": f'Consistent with "{habit.name}"!',
                    "message": (
                        f'You\'ve completed "{habit.name}" {completions} out of '
                        f"the last 14 days. Excellent consistency!"
                    ),
                    "confidence_score": 0.9,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Habit '{habit.name}' completed "
                        f"{completions}/14 days (threshold: 5)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "habit_id": habit.id,
                        "habit_name": habit.name,
                        "completions_14d": completions,
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type,
                        str(window_start),
                        str(today),
                        [habit.id],
                    ),
                }
            )

        return insights
