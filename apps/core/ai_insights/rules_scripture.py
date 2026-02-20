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
        from apps.faith.models import UserReadingProgress

        now = get_current_time()
        # Check last 12 days for daily reading, then 5-day gap
        recent_window = now - timedelta(days=12)
        recent_completions = (
            UserReadingProgress.objects.filter(
                user=user,
                is_completed=True,
                completed_at__gte=recent_window,
                completed_at__lte=now - timedelta(days=3),
            )
            .values_list("completed_at__date", flat=True)
            .distinct()
        )

        daily_count = len(set(recent_completions))
        if daily_count < 1:
            return []

        # Check if there's been a 5-day gap
        latest = (
            UserReadingProgress.objects.filter(
                user=user, is_completed=True
            )
            .order_by("-completed_at")
            .first()
        )

        if not latest or not latest.completed_at:
            return []

        gap_days = (now - latest.completed_at).days
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
                    "last_reading_date": str(latest.completed_at.date()),
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                ),
            }
        ]
