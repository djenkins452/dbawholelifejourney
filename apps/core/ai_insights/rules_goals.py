"""
Goals Insight Rules — Completion tracking, deadline risk, and stagnation detection.
"""

from datetime import date, timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register
from apps.core.time.system_clock import get_current_time


@register
class GoalProgressRule(BaseInsightRule):
    """
    Produce an insight when a milestone or goal is completed.

    Triggers on fire_intelligence() calls with action 'complete_milestone'
    or 'complete_goal'. Produces a 'positive' insight with progress data
    so the signal pipeline sees activity in the 'purpose' domain.
    """

    rule_name = "goal_progress"
    module = "purpose"
    insight_type = "goal_progress"
    min_confidence_to_store = 0.5  # Always store completion insights

    def applies(self, user, event):
        if event.get("module") != "purpose":
            return False
        return event.get("action") in ("complete_milestone", "complete_goal")

    def evaluate(self, user, event):
        action = event.get("action")
        record_id = event.get("record_id")
        today = date.today()
        window_start, window_end = get_time_window(days=1)

        if action == "complete_milestone":
            return self._evaluate_milestone(user, record_id, today, window_start, window_end)
        elif action == "complete_goal":
            return self._evaluate_goal(user, record_id, today, window_start, window_end)
        return []

    def _evaluate_milestone(self, user, milestone_id, today, window_start, window_end):
        from apps.purpose.models import GoalMilestone

        try:
            milestone = GoalMilestone.objects.select_related("goal").get(
                pk=milestone_id, goal__user=user,
            )
        except GoalMilestone.DoesNotExist:
            return []

        goal = milestone.goal
        total = goal.milestones.count()
        completed = goal.milestones.filter(completed=True).count()
        progress_pct = round(completed / total * 100) if total > 0 else 0

        return [
            {
                "severity": "positive",
                "title": f'Milestone completed: "{milestone.title}"',
                "message": (
                    f'You completed milestone "{milestone.title}" on goal '
                    f'"{goal.title}". Progress: {completed}/{total} '
                    f"milestones ({progress_pct}%)."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User completed milestone "
                    f"'{milestone.title}' (id={milestone.id}) on goal "
                    f"'{goal.title}' (id={goal.id}). "
                    f"{completed}/{total} milestones done ({progress_pct}%)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "action": "complete_milestone",
                    "milestone_id": milestone.id,
                    "milestone_title": milestone.title,
                    "goal_id": goal.id,
                    "goal_title": goal.title,
                    "milestones_total": total,
                    "milestones_completed": completed,
                    "progress_pct": progress_pct,
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    [milestone.id],
                ),
            }
        ]

    def _evaluate_goal(self, user, goal_id, today, window_start, window_end):
        from apps.purpose.models import LifeGoal

        try:
            # Use all_objects: goal was just completed (status != "active")
            goal = LifeGoal.all_objects.get(pk=goal_id, user=user)
        except LifeGoal.DoesNotExist:
            return []

        return [
            {
                "severity": "positive",
                "title": f'Goal completed: "{goal.title}"',
                "message": (
                    f'Congratulations! You completed your goal "{goal.title}". '
                    f"This is a significant achievement."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User completed goal "
                    f"'{goal.title}' (id={goal.id})."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "action": "complete_goal",
                    "goal_id": goal.id,
                    "goal_title": goal.title,
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    [goal.id],
                ),
            }
        ]


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

        stale_threshold = get_current_time() - timedelta(days=14)

        goals = LifeGoal.objects.filter(
            user=user,
            status="active",
            updated_at__lt=stale_threshold,
        )

        insights = []
        window_start, window_end = get_time_window(days=14)

        for goal in goals:
            days_stale = (get_current_time() - goal.updated_at).days

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
