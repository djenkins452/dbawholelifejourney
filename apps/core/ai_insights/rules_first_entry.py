"""
First-Entry Insight Rules — Instant positive reinforcement on first data point.

These rules fire exactly once per domain, the very first time a user
logs any data in that domain. This ensures new users get immediate
feedback and motivation rather than silence.
"""

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.rule_registry import register


@register
class FirstWeightEntryRule(BaseInsightRule):
    rule_name = "first_weight_entry"
    module = "health"
    insight_type = "first_weight_entry"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "log_weight",
            "update_weight",
        )

    def evaluate(self, user, event):
        from apps.health.models import WeightEntry

        count = WeightEntry.objects.filter(user=user, status="active").count()
        if count != 1:
            return []

        entry = WeightEntry.objects.filter(user=user, status="active").first()
        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "First weight entry logged!",
                "message": (
                    f"Great start! You've logged your first weight entry at "
                    f"{entry.value} {entry.unit}. "
                    f"Consistent tracking is the foundation of progress. "
                    f"Keep logging to unlock trend insights and predictions."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User logged their first weight entry."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "entry_id": entry.id,
                    "value": float(entry.value),
                    "unit": entry.unit,
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstJournalEntryRule(BaseInsightRule):
    rule_name = "first_journal_entry"
    module = "journal"
    insight_type = "first_journal_entry"

    def applies(self, user, event):
        return event.get("module") == "journal" and event.get("action") in (
            "create_journal_entry",
        )

    def evaluate(self, user, event):
        from apps.journal.models import JournalEntry

        count = JournalEntry.objects.filter(user=user, status="active").count()
        if count != 1:
            return []

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "Your journaling journey begins!",
                "message": (
                    "You've written your first journal entry. "
                    "Journaling builds self-awareness and helps process thoughts. "
                    "Keep writing to build a streak and unlock deeper insights."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User created their first journal entry."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstHabitLogRule(BaseInsightRule):
    rule_name = "first_habit_log"
    module = "purpose"
    insight_type = "first_habit_log"

    def applies(self, user, event):
        return event.get("module") == "purpose" and event.get("action") in (
            "log_habit",
        )

    def evaluate(self, user, event):
        from apps.purpose.models import HabitEntry

        count = HabitEntry.objects.filter(
            goal__user=user, completed=True
        ).count()
        if count != 1:
            return []

        entry = HabitEntry.objects.filter(
            goal__user=user, completed=True
        ).select_related("goal").first()

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "First habit completed!",
                "message": (
                    f'You completed "{entry.goal.name}" for the first time. '
                    f"Every great habit starts with a single step. "
                    f"Keep it up to build momentum!"
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User completed their first habit entry."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "habit_id": entry.goal.id,
                    "habit_name": entry.goal.name,
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstScriptureReadingRule(BaseInsightRule):
    rule_name = "first_scripture_reading"
    module = "faith"
    insight_type = "first_scripture_reading"

    def applies(self, user, event):
        return event.get("module") == "faith" and event.get("action") in (
            "complete_reading",
        )

    def evaluate(self, user, event):
        from apps.faith.models import UserReadingProgress

        count = UserReadingProgress.objects.filter(
            user=user, is_completed=True
        ).count()
        if count != 1:
            return []

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "Scripture reading journey begun!",
                "message": (
                    "You've completed your first scripture reading. "
                    "Consistent reading deepens understanding and strengthens faith. "
                    "Keep going to build a reading streak!"
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User completed their first scripture reading."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstBodyCompEntryRule(BaseInsightRule):
    rule_name = "first_body_comp_entry"
    module = "health"
    insight_type = "first_body_comp_entry"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "log_body_comp",
        )

    def evaluate(self, user, event):
        from apps.health.models import BodyCompositionEntry

        count = BodyCompositionEntry.objects.filter(
            user=user, status="active"
        ).count()
        if count != 1:
            return []

        entry = BodyCompositionEntry.objects.filter(
            user=user, status="active"
        ).first()

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "Body composition baseline set!",
                "message": (
                    f"You've logged your first body composition measurement "
                    f"({entry.metric_name}: {entry.value}). "
                    f"This baseline helps track changes beyond the scale. "
                    f"Log again in a few weeks to see your progress."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User logged their first body comp entry."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "entry_id": entry.id,
                    "metric_name": entry.metric_name,
                    "value": float(entry.value),
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstWorkoutRule(BaseInsightRule):
    rule_name = "first_workout"
    module = "health"
    insight_type = "first_workout"

    def applies(self, user, event):
        return event.get("module") == "health" and event.get("action") in (
            "log_workout",
        )

    def evaluate(self, user, event):
        from apps.health.models import WorkoutSession

        count = WorkoutSession.objects.filter(user=user, status="active").count()
        if count != 1:
            return []

        session = WorkoutSession.objects.filter(
            user=user, status="active"
        ).first()

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "First workout logged!",
                "message": (
                    f"You've logged your first workout"
                    f"{' — ' + session.name if session.name else ''}! "
                    f"Tracking workouts helps identify patterns and measure progress. "
                    f"Keep logging to unlock strength progression predictions."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User logged their first workout."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "session_id": session.id,
                },
                "dedupe_key": dedupe_key,
            }
        ]


@register
class FirstGoalCreatedRule(BaseInsightRule):
    rule_name = "first_goal_created"
    module = "purpose"
    insight_type = "first_goal_created"

    def applies(self, user, event):
        return event.get("module") == "purpose" and event.get("action") in (
            "create_goal",
        )

    def evaluate(self, user, event):
        from apps.purpose.models import LifeGoal

        count = LifeGoal.objects.filter(user=user, status="active").count()
        if count != 1:
            return []

        goal = LifeGoal.objects.filter(user=user, status="active").first()

        dedupe_key = build_dedupe_key(user.id, self.insight_type, "first")

        return [
            {
                "severity": "positive",
                "title": "First goal set!",
                "message": (
                    f'You\'ve created your first goal: "{goal.title}". '
                    f"Setting clear goals is the first step to achieving them. "
                    f"Add milestones to track your progress toward this goal."
                ),
                "confidence_score": 1.0,
                "explain_why": (
                    f"Rule: {self.rule_name}. User created their first life goal."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "goal_id": goal.id,
                    "goal_title": goal.title,
                },
                "dedupe_key": dedupe_key,
            }
        ]
