"""
PRIE — Habit prediction rules.

Predictions:
- Habit continuation probability (will user keep the habit?)
"""

from datetime import timedelta

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.time.system_clock import get_current_time


@register_prediction
class HabitContinuationRule(BasePredictionRule):
    """
    Predict probability a user will continue an active habit
    based on recent completion rate and trend.
    """

    rule_name = "habit_continuation"
    module = "habits"
    prediction_type = "habit_continuation"
    min_confidence_to_store = 0.25

    LOOKBACK_DAYS = 28  # 4 weeks

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "habits", "purpose")

    def predict(self, user, event):
        from apps.purpose.models import HabitGoal

        habits = HabitGoal.objects.filter(user=user, status="active")
        now = get_current_time()
        predictions = []

        for habit in habits:
            cutoff = (now - timedelta(days=self.LOOKBACK_DAYS)).date()
            entries = habit.habit_entries.filter(date__gte=cutoff).order_by("date")

            total_entries = entries.count()
            if total_entries < 3:
                continue

            completed = entries.filter(completed=True).count()

            # Calculate completion rate
            # For daily habits, expected = LOOKBACK_DAYS
            # For weekly habits, expected = LOOKBACK_DAYS / 7
            if habit.frequency_type == "weekly":
                expected = self.LOOKBACK_DAYS / 7
                sessions = habit.sessions_per_week or 1
                expected *= sessions
            elif habit.frequency_type == "monthly":
                expected = self.LOOKBACK_DAYS / 30
            else:
                expected = self.LOOKBACK_DAYS

            completion_rate = completed / max(1, expected)
            completion_rate = min(1.0, completion_rate)

            # Check recent trend (last 7 days vs previous 7 days)
            recent_cutoff = (now - timedelta(days=7)).date()
            prior_cutoff = (now - timedelta(days=14)).date()

            recent_completed = entries.filter(
                date__gte=recent_cutoff, completed=True
            ).count()
            prior_completed = entries.filter(
                date__gte=prior_cutoff,
                date__lt=recent_cutoff,
                completed=True,
            ).count()

            # Trend factor
            if prior_completed > 0:
                trend_ratio = recent_completed / prior_completed
            elif recent_completed > 0:
                trend_ratio = 1.5  # improving from zero
            else:
                trend_ratio = 0.5  # both periods empty

            # Continuation probability
            # Base = completion rate, adjusted by trend
            if trend_ratio >= 1.0:
                trend_boost = min(0.15, (trend_ratio - 1.0) * 0.1)
            else:
                trend_boost = max(-0.20, (trend_ratio - 1.0) * 0.15)

            continuation_prob = min(1.0, max(0.0, completion_rate + trend_boost))

            # Confidence
            if total_entries >= 20:
                confidence = 0.75
            elif total_entries >= 10:
                confidence = 0.55
            else:
                confidence = 0.35

            conf = confidence_label(confidence)
            pred_type = f"habit_continuation_{habit.id}"
            date_str = (now + timedelta(days=30)).strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            if continuation_prob >= 0.8:
                outlook = "very likely to continue"
            elif continuation_prob >= 0.5:
                outlook = "moderately likely to continue"
            else:
                outlook = "at risk of dropping off"

            trend_desc = (
                "trending up" if trend_ratio >= 1.1
                else "trending down" if trend_ratio <= 0.9
                else "stable"
            )

            explanation = (
                f"Habit \"{habit.name}\": {completion_rate:.0%} completion rate "
                f"over {self.LOOKBACK_DAYS} days ({completed} completions), "
                f"recent trend is {trend_desc}. "
                f"Continuation probability: {continuation_prob:.0%} — {outlook}. "
                f"Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "habits",
                    "predicted_value": round(continuation_prob, 2),
                    "predicted_date": now + timedelta(days=30),
                    "confidence_score": confidence,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "habit_id": habit.id,
                        "habit_name": habit.name,
                        "completion_rate": round(completion_rate, 2),
                        "total_entries": total_entries,
                        "completed_entries": completed,
                        "recent_completed": recent_completed,
                        "prior_completed": prior_completed,
                        "trend_ratio": round(trend_ratio, 2),
                        "continuation_probability": round(continuation_prob, 2),
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions
