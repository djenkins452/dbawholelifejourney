"""
Goals Insight Rules — Deadline risk and stagnation detection.
"""

from datetime import date, timedelta

from django.utils import timezone

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class GoalDeadlineRiskRule(BaseInsightRule):
    rule_name = "goal_deadline_risk"
    module = "purpose"
    insight_type = "goal_deadline_risk"

    def applies(self, user, event):
        return event.get("module") == "purpose" or event.get(
            "event_type"
        ) == "scheduled_check"

    def evaluate(self, user, event):
        from apps.purpose.models import LifeGoal

        today = date.today()
        deadline_window = today + timedelta(days=30)

        goals = LifeGoal.objects.filter(
            user=user,
            status="active",
            target_date__isnull=False,
            target_date__lte=deadline_window,
            target_date__gte=today,
        )

        insights = []
        for goal in goals:
            days_remaining = (goal.target_date - today).days
            window_start, window_end = get_time_window(days=30)

            insights.append(
                {
                    "severity": "warning",
                    "title": f'Goal "{goal.title}" due in {days_remaining} days',
                    "message": (
                        f'Your goal "{goal.title}" has a target date of '
                        f"{goal.target_date.strftime('%B %d, %Y')} "
                        f"({days_remaining} days remaining). "
                        f"Consider reviewing your progress."
                    ),
                    "confidence_score": 0.8,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Goal '{goal.title}' target_date="
                        f"{goal.target_date}, {days_remaining} days remaining "
                        f"(threshold: 30 days)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "goal_id": goal.id,
                        "goal_title": goal.title,
                        "target_date": str(goal.target_date),
                        "days_remaining": days_remaining,
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type,
                        window_start.date(),
                        window_end.date(),
                        [goal.id],
                    ),
                }
            )

        return insights


@register
class GoalStagnationRule(BaseInsightRule):
    rule_name = "goal_stagnation"
    module = "purpose"
    insight_type = "goal_stagnation"

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.purpose.models import LifeGoal

        stale_threshold = timezone.now() - timedelta(days=14)

        goals = LifeGoal.objects.filter(
            user=user,
            status="active",
            updated_at__lt=stale_threshold,
        )

        insights = []
        window_start, window_end = get_time_window(days=14)

        for goal in goals:
            days_stale = (timezone.now() - goal.updated_at).days

            insights.append(
                {
                    "severity": "info",
                    "title": f'No updates on "{goal.title}" in {days_stale} days',
                    "message": (
                        f'Your goal "{goal.title}" hasn\'t been updated in '
                        f"{days_stale} days. A quick check-in can help "
                        f"maintain momentum."
                    ),
                    "confidence_score": 0.7,
                    "explain_why": (
                        f"Rule: {self.rule_name}. Goal '{goal.title}' last updated "
                        f"{goal.updated_at.date()}, {days_stale} days ago (threshold: 14)."
                    ),
                    "evidence": {
                        "rule_name": self.rule_name,
                        "goal_id": goal.id,
                        "goal_title": goal.title,
                        "last_updated": str(goal.updated_at.date()),
                        "days_stale": days_stale,
                    },
                    "dedupe_key": build_dedupe_key(
                        user.id,
                        self.insight_type,
                        window_start.date(),
                        window_end.date(),
                        [goal.id],
                    ),
                }
            )

        return insights
