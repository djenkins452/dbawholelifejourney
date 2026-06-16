"""
Scripture Reading Insight Rules — Drop-off detection.
"""

from datetime import timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register
from apps.core.time.system_clock import get_current_time


@register
class ScriptureReadingDropOffRule(BaseInsightRule):
    rule_name = "scripture_reading_dropoff"
    module = "faith"
    insight_type = "scripture_reading_dropoff"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.faith.services.faith_queries import FaithQueries

        now = get_current_time()
        today = now.date()
        # Canonical unified completion dates (plan + routine→faith bridge) so
        # this "paused" insight can never contradict execution truth — e.g. it
        # never fires when the user is reading daily via a routine (trust
        # contract 2026-06-16). Previously plan-only (UserReadingProgress).
        dates = FaithQueries.bible_completion_dates(user, limit=30)
        if not dates:
            return []

        # Reading days in the 3–12-days-ago window (a prior streak to contrast).
        recent_completions = [
            d for d in dates
            if (today - timedelta(days=12)) <= d <= (today - timedelta(days=3))
        ]
        daily_count = len(set(recent_completions))
        if daily_count < 1:
            return []

        # Gap since the most recent completion (ANY canonical source).
        latest = dates[0]
        gap_days = (today - latest).days
        if gap_days < 1:
            return []

        window_start, window_end = get_time_window(days=12)

        return [
            {
                "severity": "info",
                "title": "Scripture reading paused",
                "message": (
                    f"You had a great streak of {daily_count} days of scripture "
                    f"reading, but it's been {gap_days} days since your last session. "
                    f"Even a few minutes can be meaningful."
                ),
                "confidence_score": 0.8,
                "explain_why": (
                    f"Rule: {self.rule_name}. Had {daily_count} reading days in "
                    f"12-day window, then {gap_days}-day gap (threshold: 3)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "daily_reading_count": daily_count,
                    "gap_days": gap_days,
                    "last_reading_date": str(latest),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]
