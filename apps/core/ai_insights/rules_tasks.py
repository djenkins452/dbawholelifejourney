"""
Task Insight Rules — Overdue detection, stall detection, and today-relevance.

Follows the same pattern as rules_goals.py. All rules trigger on
scheduled_check events so they run automatically via the ISE batch.
"""

from datetime import date, timedelta

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register
from apps.core.time.system_clock import get_current_time


@register
class TaskOverduePatternRule(BaseInsightRule):
    """
    Generate a warning when a user has 2+ overdue tasks.

    Urgency signal: Beth should surface overdue tasks from data,
    not LLM judgment.
    """

    rule_name = "task_overdue_pattern"
    module = "life"
    insight_type = "task_overdue_pattern"
    min_confidence_to_store = 0.5

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.life.services.task_queries import TaskQueries

        today = date.today()
        overdue_qs = TaskQueries.overdue(user, today)
        overdue_tasks = list(
            overdue_qs.order_by('due_date').values('id', 'title', 'due_date')[:10]
        )

        if len(overdue_tasks) < 2:
            return []

        window_start, window_end = get_time_window(days=1)
        task_ids = [t['id'] for t in overdue_tasks]
        task_summaries = [
            f"'{t['title']}' (due {t['due_date']})" for t in overdue_tasks
        ]

        return [
            {
                "severity": "warning",
                "title": f"{len(overdue_tasks)} tasks are overdue",
                "message": (
                    f"You have {len(overdue_tasks)} overdue tasks: "
                    f"{', '.join(task_summaries[:5])}."
                    + (f" (+{len(overdue_tasks) - 5} more)" if len(overdue_tasks) > 5 else "")
                ),
                "confidence_score": 0.9,
                "explain_why": (
                    f"Rule: {self.rule_name}. User has {len(overdue_tasks)} "
                    f"pending tasks past their due date (threshold: 2)."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "overdue_count": len(overdue_tasks),
                    "tasks": [
                        {"task_id": t['id'], "task_title": t['title'],
                         "due_date": str(t['due_date'])}
                        for t in overdue_tasks
                    ],
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    task_ids,
                ),
            }
        ]


@register
class TaskStallRule(BaseInsightRule):
    """
    Detect disengagement: no tasks completed in 5+ days with pending tasks.
    """

    rule_name = "task_stall"
    module = "life"
    insight_type = "task_stall"
    min_confidence_to_store = 0.5

    STALL_DAYS = 5

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.life.services.task_queries import TaskQueries

        # Check if there are any pending tasks at all
        pending_count = TaskQueries.pending(user).count()
        if pending_count == 0:
            return []

        # Check for recent completions
        cutoff = get_current_time() - timedelta(days=self.STALL_DAYS)
        recent_completions = TaskQueries.completed_since(user, cutoff).count()

        if recent_completions > 0:
            return []

        window_start, window_end = get_time_window(days=self.STALL_DAYS)

        return [
            {
                "severity": "info",
                "title": f"No tasks completed in {self.STALL_DAYS}+ days",
                "message": (
                    f"You have {pending_count} pending tasks but haven't "
                    f"completed any in the last {self.STALL_DAYS} days. "
                    f"A quick win can help rebuild momentum."
                ),
                "confidence_score": 0.7,
                "explain_why": (
                    f"Rule: {self.rule_name}. {pending_count} pending tasks, "
                    f"0 completions in last {self.STALL_DAYS} days."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "pending_count": pending_count,
                    "days_since_last_completion": self.STALL_DAYS,
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    [],
                ),
            }
        ]


@register
class TaskDueTodayRule(BaseInsightRule):
    """
    Today-relevance signal: list tasks due today with IDs and priorities.

    Enables deterministic "what matters today" instead of LLM guessing.
    """

    rule_name = "task_due_today"
    module = "life"
    insight_type = "task_due_today"
    min_confidence_to_store = 0.5

    MAX_TASKS = 5

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        from apps.life.services.task_queries import TaskQueries
        from django.db.models import Case, When, Value

        today = date.today()

        # Tasks due today (by due_date or scheduled_date)
        due_today_qs = TaskQueries.pending(user).filter(
            due_date=today,
        ).order_by(
            Case(
                When(priority='now', then=Value(0)),
                When(priority='soon', then=Value(1)),
                When(priority='someday', then=Value(2)),
                default=Value(3),
            ),
            'scheduled_time',
        )

        due_today = list(
            due_today_qs.values('id', 'title', 'priority', 'scheduled_time')[
                :self.MAX_TASKS
            ]
        )
        total_due = due_today_qs.count()

        if total_due == 0:
            return []

        window_start, window_end = get_time_window(days=1)
        task_ids = [t['id'] for t in due_today]
        task_summaries = []
        for t in due_today:
            time_str = (
                f" at {t['scheduled_time'].strftime('%H:%M')}"
                if t.get('scheduled_time') else ""
            )
            task_summaries.append(
                f"'{t['title']}' ({t['priority']}{time_str})"
            )

        return [
            {
                "severity": "info",
                "title": f"{total_due} task{'s' if total_due != 1 else ''} due today",
                "message": (
                    f"Tasks due today: {', '.join(task_summaries)}."
                    + (f" (+{total_due - len(due_today)} more)" if total_due > len(due_today) else "")
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. {total_due} pending tasks "
                    f"with due_date={today}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "total_due_today": total_due,
                    "tasks": [
                        {
                            "task_id": t['id'],
                            "task_title": t['title'],
                            "priority": t['priority'],
                            "scheduled_time": (
                                str(t['scheduled_time']) if t.get('scheduled_time') else None
                            ),
                        }
                        for t in due_today
                    ],
                },
                "dedupe_key": build_dedupe_key(
                    user.id,
                    self.insight_type,
                    window_start.date(),
                    window_end.date(),
                    task_ids,
                ),
            }
        ]
