"""
PRIE — Goal prediction rules.

Predictions:
- Predicted goal completion date based on progress velocity
"""

from datetime import timedelta

from django.utils import timezone

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction


@register_prediction
class GoalCompletionDateRule(BasePredictionRule):
    """
    Predict when an active goal will be completed based on
    milestone/progress update velocity.
    """

    rule_name = "goal_completion_date"
    module = "goals"
    prediction_type = "goal_completion_date"
    min_confidence_to_store = 0.25

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "goals", "purpose")

    def predict(self, user, event):
        from apps.purpose.models import LifeGoal

        goals = LifeGoal.objects.filter(
            user=user,
            status="active",
            target_date__isnull=False,
        )

        predictions = []
        now = timezone.now()

        for goal in goals:
            # Calculate progress based on milestone completions
            milestones = goal.milestones.all()
            total = milestones.count()
            if total == 0:
                continue

            completed = milestones.filter(completed=True).count()
            if completed == 0:
                continue

            # Find earliest and latest milestone completion
            completed_milestones = milestones.filter(
                completed=True,
                completed_date__isnull=False,
            ).order_by("completed_date")

            if completed_milestones.count() < 1:
                continue

            first_completion = completed_milestones.first().completed_date
            last_completion = completed_milestones.last().completed_date

            # Calculate velocity (milestones per day)
            days_active = max(1, (last_completion - first_completion).days)
            if completed_milestones.count() == 1:
                # Only one milestone — estimate from goal creation to now
                days_active = max(1, (now.date() - goal.created_at.date()).days)

            velocity = completed / days_active  # milestones per day
            remaining = total - completed

            if velocity <= 0:
                continue

            days_to_completion = remaining / velocity
            predicted_completion = now + timedelta(days=days_to_completion)

            # Confidence factors
            progress_pct = completed / total
            if progress_pct >= 0.5:
                base_conf = 0.65
            elif progress_pct >= 0.25:
                base_conf = 0.45
            else:
                base_conf = 0.30

            # Boost for more completed milestones
            if completed >= 5:
                base_conf += 0.10
            elif completed >= 3:
                base_conf += 0.05

            confidence = min(1.0, base_conf)

            # Compare to target date
            target = timezone.make_aware(
                timezone.datetime.combine(goal.target_date, timezone.datetime.min.time())
            )
            days_diff = (predicted_completion - target).days
            if days_diff > 0:
                on_track = f"{days_diff} days behind schedule"
            elif days_diff < 0:
                on_track = f"{abs(days_diff)} days ahead of schedule"
            else:
                on_track = "on schedule"

            conf = confidence_label(confidence)
            pred_type = f"goal_completion_{goal.id}"
            date_str = predicted_completion.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            explanation = (
                f"Goal \"{goal.title}\": {completed}/{total} milestones complete "
                f"({progress_pct:.0%}). At current pace ({velocity:.2f} milestones/day), "
                f"estimated completion is {predicted_completion.strftime('%b %d, %Y')} — "
                f"{on_track}. Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "goals",
                    "predicted_value": days_to_completion,
                    "predicted_date": predicted_completion,
                    "confidence_score": confidence,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "goal_id": goal.id,
                        "goal_title": goal.title,
                        "milestones_total": total,
                        "milestones_completed": completed,
                        "velocity_per_day": round(velocity, 4),
                        "target_date": str(goal.target_date),
                        "days_diff_from_target": days_diff,
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions
