"""
Phase 4 CoS — Cross-Domain Intelligence Rules.

Detects correlations across module boundaries that single-domain
rules cannot see. Operates on SAE state metrics — no hardcoding
for specific users.

Correlations:
1. Mood ↓ + Goal Progress ↓ → Motivation Drift
2. Sleep ↓ + Workout Intensity ↑ → Overtraining Risk
3. Financial Stress + Journal Anxiety → Financial Anxiety Cluster
4. High Weekly Pressure + Relational Drift → Overextension Risk
5. Weight ↑ + Medication Missed → Compliance Risk
6. Habit Streak Break + Mood ↓ → Behavioral Instability Pattern

Each rule:
- Generates Insight (if pattern emerging)
- Generates Prediction (if trajectory forming)
- Adjusts Guidance Priority (if risk level elevated)
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.rule_registry import register

logger = logging.getLogger(__name__)


class CrossDomainRule(BaseInsightRule):
    """Base class for cross-domain insight rules."""

    module = "cross_domain"
    min_confidence_to_store = 0.55
    min_confidence_to_notify = 0.75

    def applies(self, user, event):
        # Cross-domain rules run on scheduled checks and state updates
        return event.get("event_type") in (
            "scheduled_check",
            "state_updated",
            "record_created",
            "record_updated",
        )

    def _get_state(self, user, event):
        """Get user state from event enrichment or direct query."""
        state = event.get("user_state")
        if state:
            return state
        try:
            from apps.core.ai_state.state_engine import get_user_state
            return get_user_state(user) or {}
        except Exception:
            return {}

    def _fire_prediction(self, user, prediction_type, module, predicted_value,
                         days_ahead, confidence, explanation, evidence):
        """Fire a PRIE prediction from a cross-domain correlation."""
        try:
            from apps.core.ai_predictions.models import Prediction, build_prediction_dedupe_key
            from apps.core.time.system_clock import get_current_time

            now = get_current_time()
            predicted_date = now + timedelta(days=days_ahead)
            dedupe_key = build_prediction_dedupe_key(
                user.id, prediction_type, predicted_date.strftime("%Y-%m-%d")
            )

            # Supersede existing
            Prediction.objects.filter(
                user=user, dedupe_key=dedupe_key, status="active",
            ).update(status="superseded", updated_at=now)

            Prediction.objects.create(
                user=user,
                prediction_type=prediction_type,
                module=module,
                predicted_value=predicted_value,
                predicted_date=predicted_date,
                confidence_score=confidence,
                explanation=explanation,
                evidence=evidence,
                dedupe_key=dedupe_key,
                status="active",
            )
        except Exception as e:
            logger.debug(f"CrossDomain: prediction fire failed: {e}")

    def _elevate_guidance(self, user, module, priority_boost=-1):
        """Boost priority of active guidance items in a module."""
        try:
            from apps.core.ai_guidance.models import GuidanceItem
            items = GuidanceItem.objects.filter(
                user=user, module=module, is_active=True,
            )
            for item in items:
                new_priority = max(1, item.priority + priority_boost)
                if new_priority != item.priority:
                    item.priority = new_priority
                    item.save(update_fields=["priority"])
        except Exception as e:
            logger.debug(f"CrossDomain: guidance elevation failed: {e}")


@register
class MotivationDriftRule(CrossDomainRule):
    """Mood ↓ + Goal Progress ↓ → Motivation Drift."""

    rule_name = "cross_domain_motivation_drift"
    insight_type = "motivation_drift"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        journal = state.get("journal", {})
        goals = state.get("goals", {})

        mood_trend = journal.get("mood_trend", "stable")
        goal_progress = goals.get("avg_completion_rate", 1.0)
        overdue = goals.get("overdue_goal_count", 0)

        if mood_trend not in ("declining", "decreasing"):
            return []
        if goal_progress >= 0.5 and overdue == 0:
            return []

        confidence = 0.65
        if goal_progress < 0.3:
            confidence += 0.1
        if overdue > 2:
            confidence += 0.1

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "motivation_drift_7d", "cross_domain", goal_progress,
            7, confidence * 0.9,
            "Declining mood combined with falling goal progress suggests motivation drift.",
            {"mood_trend": mood_trend, "goal_progress": goal_progress, "overdue": overdue},
        )
        self._elevate_guidance(user, "goals")

        return [{
            "severity": "warning",
            "title": "Motivation Drift Detected",
            "message": (
                f"Your mood has been declining while goal progress is at "
                f"{goal_progress:.0%} with {overdue} overdue goal(s). "
                "This pattern often signals motivation drift — consider "
                "revisiting your priorities or adjusting timelines."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: declining mood + declining goal "
                "progress typically indicates emerging motivation drift."
            ),
            "evidence": {
                "mood_trend": mood_trend,
                "goal_progress": goal_progress,
                "overdue_goals": overdue,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class OvertrainingRiskRule(CrossDomainRule):
    """Sleep ↓ + Workout Intensity ↑ → Overtraining Risk."""

    rule_name = "cross_domain_overtraining_risk"
    insight_type = "overtraining_risk"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        health = state.get("health", {})
        fitness = state.get("fitness", {})

        sleep_avg = health.get("sleep_avg_hours_7d", 8)
        # Phase 7 Fix: workout_count_7d does not exist on health state.
        # The canonical workout count lives on fitness state as
        # workouts_7d. Read from the correct domain (audit 2026-04-08).
        workout_count_7d = fitness.get("workouts_7d", 0)
        sleep_trend = health.get("sleep_trend", "stable")

        # Need declining sleep and high workout frequency
        if sleep_avg >= 6.5 and sleep_trend != "decreasing":
            return []
        if workout_count_7d < 5:
            return []

        confidence = 0.60
        if sleep_avg < 5.5:
            confidence += 0.15
        if workout_count_7d >= 7:
            confidence += 0.1

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "overtraining_risk_7d", "cross_domain", sleep_avg,
            7, confidence * 0.85,
            "Sleep deficit combined with high workout frequency creates overtraining risk.",
            {"sleep_avg": sleep_avg, "workout_count": workout_count_7d},
        )
        self._elevate_guidance(user, "health")

        return [{
            "severity": "warning",
            "title": "Overtraining Risk",
            "message": (
                f"Sleep averaging {sleep_avg:.1f}h/night with {workout_count_7d} "
                f"workouts in 7 days. Recovery is compromised — consider a "
                "rest day or lighter session."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: declining sleep combined with high "
                "workout frequency signals overtraining risk."
            ),
            "evidence": {
                "sleep_avg_7d": sleep_avg,
                "workout_count_7d": workout_count_7d,
                "sleep_trend": sleep_trend,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class FinancialAnxietyRule(CrossDomainRule):
    """Financial Stress + Journal Anxiety → Financial Anxiety Cluster."""

    rule_name = "cross_domain_financial_anxiety"
    insight_type = "financial_anxiety_cluster"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        journal = state.get("journal", {})
        finance = state.get("finance", {})

        anxiety_mentions = journal.get("anxiety_mention_count_7d", 0)
        mood_trend = journal.get("mood_trend", "stable")
        financial_stress = finance.get("stress_indicator", False)
        budget_overspend = finance.get("budget_overspend", False)

        if not (financial_stress or budget_overspend):
            return []
        if anxiety_mentions < 2 and mood_trend not in ("declining", "decreasing"):
            return []

        confidence = 0.60
        if anxiety_mentions >= 3:
            confidence += 0.1
        if budget_overspend:
            confidence += 0.1

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        return [{
            "severity": "warning",
            "title": "Financial Anxiety Pattern",
            "message": (
                "Financial stress signals combined with anxiety-related "
                "journal entries suggest a financial anxiety cluster. "
                "Consider reviewing your financial plan or talking to "
                "someone you trust."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: financial stress indicators "
                "combined with journal anxiety mentions."
            ),
            "evidence": {
                "anxiety_mentions_7d": anxiety_mentions,
                "financial_stress": financial_stress,
                "budget_overspend": budget_overspend,
                "mood_trend": mood_trend,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class OverextensionRiskRule(CrossDomainRule):
    """High Weekly Pressure + Relational Drift → Overextension Risk."""

    rule_name = "cross_domain_overextension_risk"
    insight_type = "overextension_risk"

    def evaluate(self, user, event):
        state = self._get_state(user, event)

        # Get weekly pressure
        weekly_pressure_avg = 0
        try:
            from apps.core.blueprint.weekly_pressure import compute_weekly_pressure
            pressure = compute_weekly_pressure(user)
            weekly_pressure_avg = pressure.get("avg_load", 0)
        except Exception:
            return []

        if weekly_pressure_avg < 70:
            return []

        # Check relational drift
        relational_drift = False
        try:
            from apps.core.ai_relationships.models import Relationship
            overdue = Relationship.objects.filter(
                user=user,
                importance_tier__lte=2,
            ).count()
            # Simple heuristic: if tier 1-2 relationships exist,
            # check if any have been neglected
            if overdue > 0:
                from datetime import timedelta as td
                stale = Relationship.objects.filter(
                    user=user,
                    importance_tier__lte=2,
                    last_interaction__lt=timezone.now() - td(days=14),
                ).count()
                relational_drift = stale > 0
        except Exception:
            pass

        if not relational_drift:
            return []

        confidence = 0.65
        if weekly_pressure_avg > 85:
            confidence += 0.1

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "overextension_burnout_14d", "cross_domain",
            weekly_pressure_avg, 14, confidence * 0.8,
            "High pressure combined with relational neglect suggests overextension.",
            {"weekly_pressure": weekly_pressure_avg, "relational_drift": True},
        )

        return [{
            "severity": "warning",
            "title": "Overextension Risk",
            "message": (
                f"Your weekly pressure is at {weekly_pressure_avg}% while "
                "key relationships are showing drift. You may be overextended — "
                "consider protecting time for important people."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: high schedule pressure combined "
                "with relational neglect signals overextension."
            ),
            "evidence": {
                "weekly_pressure_avg": weekly_pressure_avg,
                "relational_drift": True,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class ComplianceRiskRule(CrossDomainRule):
    """Weight ↑ + Medication Missed → Compliance Risk."""

    rule_name = "cross_domain_compliance_risk"
    insight_type = "compliance_risk"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        health = state.get("health", {})
        medicine = state.get("medicine", {})

        weight_trend = health.get("weight_trend", "stable")
        # Phase 4 / Phase 7: medication adherence lives under the
        # `medicine` module key `adherence_7d` (0-100). The old read
        # of `health.medication_adherence_pct` was a dead branch —
        # that key is never written to the state builder; only
        # cos_context.py constructs it as a derived view. Result: the
        # rule always got the default 100 and never fired. If
        # adherence is None (user has no medications) we do not fire
        # a compliance-risk insight.
        med_adherence = medicine.get("adherence_7d")
        if med_adherence is None:
            return []

        # Phase 4: state_builder only emits "increasing" (never "up").
        if weight_trend != "increasing":
            return []
        if med_adherence >= 80:
            return []

        confidence = 0.65
        if med_adherence < 50:
            confidence += 0.15
        if weight_trend == "increasing":
            confidence += 0.05

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._elevate_guidance(user, "health")

        return [{
            "severity": "critical",
            "title": "Compliance Risk",
            "message": (
                f"Weight is trending up while medication adherence is at "
                f"{med_adherence}%. Missed medications may be contributing — "
                "please consult your healthcare provider if this persists."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: weight increase combined with "
                "medication non-adherence suggests compliance risk."
            ),
            "evidence": {
                "weight_trend": weight_trend,
                "medication_adherence_pct": med_adherence,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class BehavioralInstabilityRule(CrossDomainRule):
    """Habit Streak Break + Mood ↓ → Behavioral Instability Pattern."""

    rule_name = "cross_domain_behavioral_instability"
    insight_type = "behavioral_instability"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        habits = state.get("habits", {})
        journal = state.get("journal", {})

        streak_broken = habits.get("streak_broken_recently", False)
        completion_rate = habits.get("avg_completion_rate", 1.0)
        mood_trend = journal.get("mood_trend", "stable")

        if not streak_broken and completion_rate >= 0.6:
            return []
        if mood_trend not in ("declining", "decreasing"):
            return []

        confidence = 0.60
        if completion_rate < 0.3:
            confidence += 0.15
        if streak_broken:
            confidence += 0.1

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "behavioral_instability_7d", "cross_domain",
            completion_rate, 7, confidence * 0.85,
            "Habit disruption combined with mood decline suggests behavioral instability.",
            {"completion_rate": completion_rate, "streak_broken": streak_broken},
        )

        return [{
            "severity": "warning",
            "title": "Behavioral Instability Pattern",
            "message": (
                f"Habit completion is at {completion_rate:.0%} with a recent "
                "streak break, and mood is declining. This pattern often "
                "precedes broader behavioral drift — consider focusing on "
                "one key habit to rebuild momentum."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: habit disruption + mood decline "
                "signals behavioral instability pattern."
            ),
            "evidence": {
                "completion_rate": completion_rate,
                "streak_broken": streak_broken,
                "mood_trend": mood_trend,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


# ── Emotion-Aware Cross-Domain Rules ─────────────────────────────────


@register
class StressRecoveryRule(CrossDomainRule):
    """Emotional Stress + Poor Sleep → Recovery Needed.

    Detects when user is reporting stress/anxiety AND sleep quality is
    degraded. Cross-domain correlation is stronger than either signal alone.
    """

    rule_name = "cross_domain_stress_recovery"
    insight_type = "stress_recovery_needed"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        journal = state.get("journal", {})
        health = state.get("health", {})

        # Emotion-derived stress indicators (from Phase 2 SAE extension)
        emotion_counts = journal.get("emotion_counts_7d", {})
        stress_count = (
            emotion_counts.get("stressed", 0)
            + emotion_counts.get("anxious", 0)
            + emotion_counts.get("overwhelmed", 0)
        )
        mood_trend = journal.get("mood_trend", "stable")

        # Sleep indicators
        sleep_avg = health.get("sleep_avg_hours_7d")
        sleep_quality = health.get("sleep_quality_avg_7d")

        # Need at least one stress signal
        if stress_count < 2 and mood_trend not in ("declining", "decreasing"):
            return []

        # Need at least one sleep concern
        sleep_poor = False
        if sleep_avg is not None and sleep_avg < 6.5:
            sleep_poor = True
        if sleep_quality is not None and sleep_quality < 3.0:
            sleep_poor = True

        if not sleep_poor:
            return []

        confidence = 0.65
        if stress_count >= 3:
            confidence += 0.1
        if sleep_avg is not None and sleep_avg < 5.5:
            confidence += 0.1
        if mood_trend in ("declining", "decreasing"):
            confidence += 0.05

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "stress_recovery_7d", "cross_domain", 0.0,
            7, confidence * 0.85,
            "Stress signals combined with poor sleep suggest recovery is needed.",
            {"stress_count": stress_count, "sleep_avg": sleep_avg},
        )
        self._elevate_guidance(user, "health")

        return [{
            "severity": "warning",
            "title": "Recovery Needed — Stress + Poor Sleep",
            "message": (
                f"You've reported stress-related feelings {stress_count} times "
                f"this week, and sleep has been below target"
                f"{f' ({sleep_avg:.1f}h avg)' if sleep_avg else ''}. "
                "This combination often signals the need to prioritize recovery. "
                "Consider lighter scheduling and earlier bedtime."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: emotional stress signals combined "
                "with degraded sleep quality indicate recovery need."
            ),
            "evidence": {
                "stress_emotion_count_7d": stress_count,
                "mood_trend": mood_trend,
                "sleep_avg_hours": sleep_avg,
                "sleep_quality_avg": sleep_quality,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]


@register
class EmotionalOverloadRule(CrossDomainRule):
    """Emotional Stress + Task Overload → Overload Detected.

    When a user is stressed AND has high execution pressure (many overdue
    tasks, low completion rate), the combination suggests genuine overload
    rather than temporary emotion.
    """

    rule_name = "cross_domain_emotional_overload"
    insight_type = "emotional_overload"

    def evaluate(self, user, event):
        state = self._get_state(user, event)
        journal = state.get("journal", {})
        execution = state.get("execution", {})

        # Emotion-derived stress indicators
        emotion_counts = journal.get("emotion_counts_7d", {})
        stress_count = (
            emotion_counts.get("stressed", 0)
            + emotion_counts.get("anxious", 0)
            + emotion_counts.get("overwhelmed", 0)
        )
        mood_trend = journal.get("mood_trend", "stable")

        # Need stress signal
        if stress_count < 2 and mood_trend not in ("declining", "decreasing"):
            return []

        # Execution pressure indicators
        overdue_count = 0
        pending_count = 0
        items = execution.get("items", [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if item.get("time_status") == "overdue":
                        overdue_count += 1
                    if item.get("is_actionable"):
                        pending_count += 1

        # Need meaningful task pressure
        if overdue_count < 3 and pending_count < 8:
            return []

        confidence = 0.60
        if stress_count >= 3:
            confidence += 0.1
        if overdue_count >= 5:
            confidence += 0.1
        if mood_trend in ("declining", "decreasing"):
            confidence += 0.05

        today = timezone.now().date()
        dedupe = build_dedupe_key(
            user.id, self.insight_type,
            str(today - timedelta(days=7)), str(today),
        )

        self._fire_prediction(
            user, "emotional_overload_7d", "cross_domain", 0.0,
            7, confidence * 0.85,
            "Stress combined with high task load suggests overload risk.",
            {"stress_count": stress_count, "overdue": overdue_count},
        )

        return [{
            "severity": "warning",
            "title": "Overload Detected — Stress + High Task Load",
            "message": (
                f"You've been feeling stressed ({stress_count} times this week) "
                f"while carrying {overdue_count} overdue items and {pending_count} "
                "pending tasks. This pattern suggests genuine overload — consider "
                "deferring non-essential tasks and focusing on what matters most."
            ),
            "confidence_score": confidence,
            "explain_why": (
                "Cross-domain correlation: emotional stress signals combined "
                "with high execution pressure indicates overload."
            ),
            "evidence": {
                "stress_emotion_count_7d": stress_count,
                "mood_trend": mood_trend,
                "overdue_count": overdue_count,
                "pending_count": pending_count,
                "rule": self.rule_name,
            },
            "dedupe_key": dedupe,
        }]
