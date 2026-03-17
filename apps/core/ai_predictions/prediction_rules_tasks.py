"""
PRIE — Task prediction rules.

Predictions:
- Deadline miss risk for tasks due within 3 days, based on completion velocity.
"""

from datetime import date, timedelta

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.time.system_clock import get_current_time


@register_prediction
class TaskOverdueRiskRule(BasePredictionRule):
    """
    For tasks with due_date in the next 3 days, predict miss probability
    based on the user's recent 14-day task completion velocity.

    A user who completes 2 tasks/day with 1 task due tomorrow has low risk.
    A user who completes 0.2 tasks/day with 3 tasks due tomorrow has high risk.
    """

    rule_name = "task_overdue_risk"
    module = "life"
    prediction_type = "task_overdue_risk"
    min_confidence_to_store = 0.25

    LOOKAHEAD_DAYS = 3
    VELOCITY_WINDOW_DAYS = 14

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def predict(self, user, event):
        from apps.life.services.task_queries import TaskQueries

        today = date.today()
        deadline = today + timedelta(days=self.LOOKAHEAD_DAYS)
        now = get_current_time()

        # Tasks due in the next 3 days
        at_risk_qs = TaskQueries.pending(user).filter(
            due_date__isnull=False,
            due_date__gte=today,
            due_date__lte=deadline,
        )
        at_risk_tasks = list(
            at_risk_qs.values('id', 'title', 'due_date', 'priority')[:10]
        )

        if not at_risk_tasks:
            return []

        # Calculate 14-day completion velocity
        velocity_start = now - timedelta(days=self.VELOCITY_WINDOW_DAYS)
        completed_count = TaskQueries.completed_since(user, velocity_start).count()
        velocity = completed_count / self.VELOCITY_WINDOW_DAYS  # tasks per day

        predictions = []
        for task in at_risk_tasks:
            days_until_due = (task['due_date'] - today).days
            if days_until_due < 0:
                days_until_due = 0

            # Simple probability model:
            # If velocity >= 1 task/day and only 1 day to go, low risk
            # If velocity < 0.3 tasks/day, high risk regardless
            if velocity >= 1.0:
                miss_probability = max(0.1, 0.3 - (velocity * 0.1))
            elif velocity >= 0.5:
                miss_probability = 0.4 + (0.2 * (1.0 - velocity))
            else:
                miss_probability = min(0.9, 0.6 + (0.3 * (1.0 - velocity * 2)))

            # Adjust by time remaining: less time = higher risk
            if days_until_due == 0:
                miss_probability = min(0.95, miss_probability * 1.5)
            elif days_until_due == 1:
                miss_probability = min(0.9, miss_probability * 1.2)

            miss_probability = round(miss_probability, 2)

            # Confidence based on data quality
            confidence = min(0.85, 0.4 + (completed_count * 0.03))

            predictions.append({
                "prediction_type": self.prediction_type,
                "module": self.module,
                "predicted_value": miss_probability,
                "predicted_date": now + timedelta(days=days_until_due),
                "confidence_score": round(confidence, 2),
                "explanation": (
                    f"Task '{task['title']}' due in {days_until_due} day(s). "
                    f"Based on your recent completion rate of "
                    f"{velocity:.1f} tasks/day, the estimated miss "
                    f"probability is {miss_probability:.0%}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "task_id": task['id'],
                    "task_title": task['title'],
                    "due_date": str(task['due_date']),
                    "days_until_due": days_until_due,
                    "velocity_14d": round(velocity, 2),
                    "completed_14d": completed_count,
                    "miss_probability": miss_probability,
                },
                "dedupe_key": build_prediction_dedupe_key(
                    user.id,
                    self.prediction_type,
                    today,
                    today + timedelta(days=self.LOOKAHEAD_DAYS),
                    [task['id']],
                ),
            })

        return predictions
