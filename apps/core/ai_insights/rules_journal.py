"""
Journal Insight Rules — Streak tracking and drop-off detection.
"""

from datetime import date, timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import days_since, get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class JournalStreakPositiveRule(BaseInsightRule):
    rule_name = "journal_streak_positive"
    module = "journal"
    insight_type = "journal_streak_positive"

    def applies(self, user, event):
        return event.get("module") == "journal" or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        from apps.journal.models import JournalEntry

        today = date.today()
        # Check last 7 days for consecutive entries
        streak_days = 0
        for i in range(14):
            check_date = today - timedelta(days=i)
            has_entry = JournalEntry.objects.filter(
                user=user,
                entry_date=check_date,
                status="active",
            ).exists()
            if has_entry:
                streak_days += 1
            elif i > 0:
                break

        if streak_days < 2:
            return []

        window_start, window_end = get_time_window(days=streak_days)

        return [
            {
                "severity": "positive",
                "title": f"{streak_days}-day journaling streak!",
                "message": (
                    f"You've journaled {streak_days} days in a row. "
                    f"Consistent reflection builds self-awareness. Keep it up!"
                ),
                "confidence_score": 0.9,
                "explain_why": (
                    f"Rule: {self.rule_name}. {streak_days} consecutive days "
                    f"with journal entries (threshold: 2)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "streak_days": streak_days,
                    "streak_end": str(today),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    str(today - timedelta(days=streak_days)),
                    str(today),
                ),
            }
        ]


@register
class JournalDropOffRule(BaseInsightRule):
    rule_name = "journal_dropoff"
    module = "journal"
    insight_type = "journal_dropoff"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.journal.models import JournalEntry

        latest = (
            JournalEntry.objects.filter(user=user, status="active")
            .order_by("-entry_date")
            .first()
        )

        if not latest:
            return []

        gap_days = (date.today() - latest.entry_date).days
        if gap_days < 5:
            return []

        window_start, window_end = get_time_window(days=gap_days)

        return [
            {
                "severity": "info",
                "title": f"No journal entry in {gap_days} days",
                "message": (
                    f"Your last journal entry was {gap_days} days ago "
                    f"on {latest.entry_date.strftime('%B %d, %Y')}. "
                    f"Journaling helps process thoughts and track growth."
                ),
                "confidence_score": 0.8,
                "explain_why": (
                    f"Rule: {self.rule_name}. Last entry: {latest.entry_date}. "
                    f"Gap: {gap_days} days (threshold: 5)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "last_entry_date": str(latest.entry_date),
                    "gap_days": gap_days,
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]
