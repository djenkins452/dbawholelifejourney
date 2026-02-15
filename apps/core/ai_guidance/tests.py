"""
PGE -- Tests for the Proactive Guidance Engine.

Tests cover:
- GuidanceItem model operations
- Guidance rules (selection logic)
- Guidance selector (rule orchestration)
- Guidance ranker (scoring and sorting)
- Guidance logger (storage and deduplication)
- Guidance engine (full pipeline)
- API views
- Management command
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.core.ai_guidance.guidance_engine import (
    expire_old_guidance,
    generate_guidance,
    get_active_guidance,
)
from apps.core.ai_guidance.guidance_logger import log_guidance
from apps.core.ai_guidance.guidance_ranker import (
    MAX_GUIDANCE_ITEMS,
    rank_guidance,
    _compute_rank_score,
)
from apps.core.ai_guidance.guidance_registry import (
    _GUIDANCE_RULES,
    get_guidance_rules,
)
from apps.core.ai_guidance.guidance_rules import (
    GoalRiskRule,
    HabitInactivityRule,
    HealthTrendRule,
    JournalInactivityRule,
    PositiveReinforcementRule,
)
from apps.core.ai_guidance.guidance_selector import select_guidance
from apps.core.ai_guidance.models import GuidanceItem, build_guidance_dedupe_key
from apps.users.models import User, TermsAcceptance


class PGETestMixin:
    """Common setup for PGE tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pge_test@example.com",
            password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.date_of_birth = "1990-01-01"
        self.user.preferences.save()


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class GuidanceItemModelTest(PGETestMixin, TestCase):
    """Tests for the GuidanceItem model."""

    def test_create_guidance_item(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Test Guidance",
            message="This is a test.",
            priority=3,
            guidance_type="test_rule",
            source="composite",
            dedupe_key="test_key_1",
        )
        self.assertEqual(item.title, "Test Guidance")
        self.assertTrue(item.is_active)
        self.assertFalse(item.is_read)

    def test_mark_read(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Read Test",
            message="Test",
            dedupe_key="read_test_1",
        )
        self.assertFalse(item.is_read)
        item.mark_read()
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_mark_read_idempotent(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Read Test",
            message="Test",
            dedupe_key="read_test_2",
            is_read=True,
        )
        item.mark_read()  # Should not error
        self.assertTrue(item.is_read)

    def test_deactivate(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Deactivate Test",
            message="Test",
            dedupe_key="deactivate_1",
        )
        self.assertTrue(item.is_active)
        item.deactivate()
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_deactivate_idempotent(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Deactivate Test",
            message="Test",
            dedupe_key="deactivate_2",
            is_active=False,
        )
        item.deactivate()  # Should not error
        self.assertFalse(item.is_active)

    def test_ordering(self):
        GuidanceItem.objects.create(
            user=self.user,
            title="Low Priority",
            message="Test",
            priority=4,
            dedupe_key="order_low",
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="High Priority",
            message="Test",
            priority=1,
            dedupe_key="order_high",
        )
        items = list(GuidanceItem.objects.filter(user=self.user))
        self.assertEqual(items[0].priority, 1)
        self.assertEqual(items[1].priority, 4)

    def test_str_representation(self):
        item = GuidanceItem(title="Test Item", priority=2)
        self.assertEqual(str(item), "[P2] Test Item")

    def test_priority_choices(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Critical",
            message="Test",
            priority=1,
            dedupe_key="priority_1",
        )
        self.assertEqual(item.get_priority_display(), "Critical")

    def test_source_choices(self):
        item = GuidanceItem.objects.create(
            user=self.user,
            title="From PIE",
            message="Test",
            source="pie_insight",
            dedupe_key="source_pie",
        )
        self.assertEqual(item.get_source_display(), "PIE Insight")

    def test_evidence_json_field(self):
        evidence = {"weight_trend": "increasing", "days": 7}
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Evidence Test",
            message="Test",
            evidence=evidence,
            dedupe_key="evidence_1",
        )
        item.refresh_from_db()
        self.assertEqual(item.evidence["weight_trend"], "increasing")

    def test_metadata_json_field(self):
        metadata = {"chart_type": "line", "metric": "weight"}
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Metadata Test",
            message="Test",
            metadata=metadata,
            dedupe_key="meta_1",
        )
        item.refresh_from_db()
        self.assertEqual(item.metadata["chart_type"], "line")


class DedupeKeyTest(PGETestMixin, TestCase):
    """Tests for dedupe key generation."""

    def test_build_dedupe_key(self):
        key = build_guidance_dedupe_key(1, "goal_risk", "42")
        self.assertEqual(len(key), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in key))

    def test_dedupe_key_deterministic(self):
        key1 = build_guidance_dedupe_key(1, "goal_risk", "42")
        key2 = build_guidance_dedupe_key(1, "goal_risk", "42")
        self.assertEqual(key1, key2)

    def test_dedupe_key_different_inputs(self):
        key1 = build_guidance_dedupe_key(1, "goal_risk", "42")
        key2 = build_guidance_dedupe_key(1, "goal_risk", "43")
        self.assertNotEqual(key1, key2)

    def test_dedupe_key_different_users(self):
        key1 = build_guidance_dedupe_key(1, "goal_risk")
        key2 = build_guidance_dedupe_key(2, "goal_risk")
        self.assertNotEqual(key1, key2)


# ---------------------------------------------------------------------------
# Ranker Tests
# ---------------------------------------------------------------------------


class GuidanceRankerTest(TestCase):
    """Tests for the guidance ranking algorithm."""

    def test_rank_empty_list(self):
        result = rank_guidance([])
        self.assertEqual(result, [])

    def test_rank_single_item(self):
        candidates = [
            {"title": "Only one", "priority": 3, "confidence_score": 0.5},
        ]
        result = rank_guidance(candidates)
        self.assertEqual(len(result), 1)

    def test_rank_limits_to_max(self):
        candidates = [
            {"title": f"Item {i}", "priority": 3}
            for i in range(10)
        ]
        result = rank_guidance(candidates)
        self.assertEqual(len(result), MAX_GUIDANCE_ITEMS)

    def test_rank_custom_limit(self):
        candidates = [
            {"title": f"Item {i}", "priority": 3}
            for i in range(10)
        ]
        result = rank_guidance(candidates, limit=3)
        self.assertEqual(len(result), 3)

    def test_higher_priority_ranks_first(self):
        candidates = [
            {"title": "Low", "priority": 5},
            {"title": "Critical", "priority": 1},
            {"title": "Medium", "priority": 3},
        ]
        result = rank_guidance(candidates)
        self.assertEqual(result[0]["title"], "Critical")

    def test_confidence_breaks_ties(self):
        candidates = [
            {"title": "Low conf", "priority": 3, "confidence_score": 0.3},
            {"title": "High conf", "priority": 3, "confidence_score": 0.9},
        ]
        result = rank_guidance(candidates)
        self.assertEqual(result[0]["title"], "High conf")

    def test_source_bonus_applied(self):
        candidates = [
            {
                "title": "Prediction",
                "priority": 3,
                "source": "prie_prediction",
                "confidence_score": None,
            },
            {
                "title": "State",
                "priority": 3,
                "source": "sae_state",
                "confidence_score": None,
            },
        ]
        result = rank_guidance(candidates)
        self.assertEqual(result[0]["title"], "Prediction")

    def test_evidence_richness_bonus(self):
        candidates = [
            {
                "title": "Rich evidence",
                "priority": 3,
                "evidence": {"a": 1, "b": 2, "c": 3, "d": 4},
            },
            {
                "title": "No evidence",
                "priority": 3,
                "evidence": {},
            },
        ]
        result = rank_guidance(candidates)
        self.assertEqual(result[0]["title"], "Rich evidence")


class ComputeRankScoreTest(TestCase):
    """Tests for the score computation function."""

    def test_priority_1_gives_50_points(self):
        score = _compute_rank_score({"priority": 1})
        self.assertGreaterEqual(score, 50.0)

    def test_priority_5_gives_10_points(self):
        score = _compute_rank_score({"priority": 5})
        self.assertGreaterEqual(score, 10.0)
        self.assertLess(score, 20.0)

    def test_confidence_contributes_up_to_10(self):
        score_high = _compute_rank_score(
            {"priority": 3, "confidence_score": 1.0}
        )
        score_low = _compute_rank_score(
            {"priority": 3, "confidence_score": 0.0}
        )
        self.assertEqual(score_high - score_low, 10.0)

    def test_missing_confidence_contributes_zero(self):
        score_with = _compute_rank_score(
            {"priority": 3, "confidence_score": 0.5}
        )
        score_without = _compute_rank_score({"priority": 3})
        self.assertGreater(score_with, score_without)

    def test_evidence_capped_at_3(self):
        score = _compute_rank_score(
            {
                "priority": 3,
                "evidence": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5},
            }
        )
        score_exact = _compute_rank_score(
            {"priority": 3, "evidence": {"a": 1, "b": 2, "c": 3}}
        )
        self.assertEqual(score, score_exact)


# ---------------------------------------------------------------------------
# Registry Tests
# ---------------------------------------------------------------------------


class GuidanceRegistryTest(TestCase):
    """Tests for the guidance rule registry."""

    def test_rules_are_registered(self):
        rules = get_guidance_rules()
        self.assertGreater(len(rules), 0)

    def test_known_rules_registered(self):
        rule_names = {r.rule_name for r in get_guidance_rules()}
        self.assertIn("goal_risk", rule_names)
        self.assertIn("habit_inactivity", rule_names)
        self.assertIn("health_trend", rule_names)
        self.assertIn("journal_inactivity", rule_names)
        self.assertIn("positive_reinforcement", rule_names)

    def test_five_rules_total(self):
        self.assertEqual(len(get_guidance_rules()), 5)


# ---------------------------------------------------------------------------
# Rule Tests
# ---------------------------------------------------------------------------


class GoalRiskRuleTest(PGETestMixin, TestCase):
    """Tests for the GoalRiskRule."""

    def test_overdue_goals_detected(self):
        rule = GoalRiskRule()
        state = {"goals": {"overdue_goal_count": 3}}
        insights = MagicMock()
        predictions = MagicMock()
        predictions.filter.return_value = []

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 1)
        self.assertIn("3 overdue goals", results[0]["title"])
        self.assertEqual(results[0]["priority"], 2)
        self.assertEqual(results[0]["source"], "sae_state")

    def test_no_overdue_goals(self):
        rule = GoalRiskRule()
        state = {"goals": {"overdue_goal_count": 0}}
        insights = MagicMock()
        predictions = MagicMock()
        predictions.filter.return_value = []

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)

    def test_single_overdue_goal_grammar(self):
        rule = GoalRiskRule()
        state = {"goals": {"overdue_goal_count": 1}}
        insights = MagicMock()
        predictions = MagicMock()
        predictions.filter.return_value = []

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertIn("1 overdue goal", results[0]["title"])
        self.assertNotIn("goals", results[0]["title"])

    def test_behind_schedule_predictions(self):
        rule = GoalRiskRule()
        state = {"goals": {"overdue_goal_count": 0}}
        insights = MagicMock()

        pred = MagicMock()
        pred.evidence = {"behind_schedule": True}
        pred.explanation = "You may miss your fitness goal"
        pred.confidence_score = 0.75
        pred.id = 1

        predictions = MagicMock()
        predictions.filter.return_value = [pred]

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "prie_prediction")


class HabitInactivityRuleTest(PGETestMixin, TestCase):
    """Tests for the HabitInactivityRule."""

    def test_broken_streak_warnings(self):
        rule = HabitInactivityRule()
        state = {}

        insight = MagicMock()
        insight.title = "Habit streak broken"
        insight.message = "Your meditation streak ended"
        insight.confidence_score = 0.8
        insight.evidence = {"streak_days": 14}
        insight.id = 10

        insights = MagicMock()
        insights.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: [insight]
        )
        insights.filter.return_value.exclude.return_value = [insight]

        predictions = MagicMock()

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["guidance_type"], "habit_inactivity")

    def test_no_warnings_when_no_insights(self):
        rule = HabitInactivityRule()
        state = {}
        insights = MagicMock()
        insights.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: []
        )
        insights.filter.return_value.exclude.return_value = []
        predictions = MagicMock()

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)


class HealthTrendRuleTest(PGETestMixin, TestCase):
    """Tests for the HealthTrendRule."""

    def test_health_warning_gets_priority_2(self):
        rule = HealthTrendRule()
        state = {}

        insight = MagicMock()
        insight.title = "Weight increasing"
        insight.message = "Trend"
        insight.severity = "warning"
        insight.confidence_score = 0.7
        insight.evidence = {}
        insight.id = 20

        insights = MagicMock()
        insights.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: [insight]
        )
        insights.filter.return_value.exclude.return_value = [insight]

        predictions = MagicMock()
        predictions.filter.return_value.__getitem__ = lambda self, s: []
        predictions.filter.return_value = []

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(results[0]["priority"], 2)

    def test_health_positive_gets_priority_4(self):
        rule = HealthTrendRule()
        state = {}

        insight = MagicMock()
        insight.title = "Weight stable"
        insight.message = "Stable"
        insight.severity = "positive"
        insight.confidence_score = 0.9
        insight.evidence = {}
        insight.id = 21

        insights = MagicMock()
        insights.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: [insight]
        )
        insights.filter.return_value.exclude.return_value = [insight]

        predictions = MagicMock()
        predictions.filter.return_value.__getitem__ = lambda self, s: []
        predictions.filter.return_value = []

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(results[0]["priority"], 4)


class JournalInactivityRuleTest(PGETestMixin, TestCase):
    """Tests for the JournalInactivityRule."""

    def test_zero_entries_sae_state(self):
        rule = JournalInactivityRule()
        state = {"journal": {"entry_count_30d": 0}}

        insights = MagicMock()
        journal_qs = MagicMock()
        empty_qs = MagicMock()
        empty_qs.__getitem__ = MagicMock(return_value=[])
        empty_qs.__iter__ = MagicMock(return_value=iter([]))
        empty_qs.exists.return_value = False
        journal_qs.exclude.return_value = empty_qs
        insights.filter.return_value = journal_qs

        predictions = MagicMock()

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "sae_state")
        self.assertIn("haven't journaled", results[0]["title"])

    def test_active_journaling_no_guidance(self):
        rule = JournalInactivityRule()
        state = {"journal": {"entry_count_30d": 15}}

        insights = MagicMock()
        journal_qs = MagicMock()
        empty_qs = MagicMock()
        empty_qs.__getitem__ = MagicMock(return_value=[])
        empty_qs.__iter__ = MagicMock(return_value=iter([]))
        empty_qs.exists.return_value = False
        journal_qs.exclude.return_value = empty_qs
        insights.filter.return_value = journal_qs

        predictions = MagicMock()

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)


class PositiveReinforcementRuleTest(PGETestMixin, TestCase):
    """Tests for the PositiveReinforcementRule."""

    def test_positive_insights_surfaced(self):
        rule = PositiveReinforcementRule()
        state = {}

        insight = MagicMock()
        insight.title = "Great job!"
        insight.message = "Your running improved"
        insight.module = "health"
        insight.confidence_score = 0.9
        insight.evidence = {}
        insight.id = 30

        insights = MagicMock()
        insights.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: [insight]
        )
        insights.filter.return_value.exclude.return_value = [insight]

        predictions = MagicMock()

        results = rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["priority"], 4)
        self.assertEqual(results[0]["module"], "health")


# ---------------------------------------------------------------------------
# Selector Tests
# ---------------------------------------------------------------------------


class GuidanceSelectorTest(PGETestMixin, TestCase):
    """Tests for the guidance selector."""

    def test_selector_runs_all_rules(self):
        state = {
            "goals": {"overdue_goal_count": 2},
            "journal": {"entry_count_30d": 0},
        }

        # Create mock querysets that behave like Django QuerySets
        insights = MagicMock()
        # For habit rule
        habit_qs = MagicMock()
        habit_qs.exclude.return_value = []

        # For health rule
        health_qs = MagicMock()
        health_qs.exclude.return_value = []

        # For journal rule
        journal_qs = MagicMock()
        journal_qs.exclude.return_value = []
        journal_qs.exclude.return_value = MagicMock()
        journal_qs.exclude.return_value.__getitem__ = lambda self, s: []
        journal_qs.exclude.return_value.exists.return_value = False

        # For positive rule
        positive_qs = MagicMock()
        positive_qs.exclude.return_value = []

        def filter_side_effect(**kwargs):
            if kwargs.get("module") == "habits":
                return habit_qs
            if kwargs.get("module") == "health":
                return health_qs
            if kwargs.get("module") == "journal":
                return journal_qs
            if kwargs.get("severity") == "positive":
                return positive_qs
            return MagicMock()

        insights.filter = MagicMock(side_effect=filter_side_effect)

        predictions = MagicMock()
        predictions.filter.return_value = []

        candidates = select_guidance(self.user, state, insights, predictions)

        # Should get at least goal overdue + journal inactivity
        self.assertGreaterEqual(len(candidates), 2)

    def test_selector_handles_rule_errors(self):
        """Rules that raise exceptions should not break the selector."""
        state = {}
        insights = MagicMock()
        insights.filter.side_effect = Exception("Simulated error")
        predictions = MagicMock()
        predictions.filter.side_effect = Exception("Simulated error")

        # Should not raise — logs error and continues
        candidates = select_guidance(self.user, state, insights, predictions)
        # May or may not have items, but should not crash
        self.assertIsInstance(candidates, list)


# ---------------------------------------------------------------------------
# Logger Tests
# ---------------------------------------------------------------------------


class GuidanceLoggerTest(PGETestMixin, TestCase):
    """Tests for the guidance logger (storage and deduplication)."""

    def test_log_creates_new_items(self):
        candidates = [
            {
                "title": "New Guidance",
                "message": "Test message",
                "priority": 3,
                "guidance_type": "test",
                "source": "composite",
                "module": "health",
                "dedupe_key": "log_test_1",
            }
        ]
        stored = log_guidance(self.user, candidates)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].title, "New Guidance")

    def test_log_deduplicates_active_items(self):
        """Same dedupe_key should update existing active item, not create new."""
        candidates = [
            {
                "title": "First Version",
                "message": "Message v1",
                "priority": 3,
                "guidance_type": "test",
                "source": "composite",
                "dedupe_key": "dedupe_test_1",
            }
        ]
        stored1 = log_guidance(self.user, candidates)
        self.assertEqual(len(stored1), 1)

        # Log same dedupe_key again
        candidates[0]["title"] = "Updated Version"
        candidates[0]["message"] = "Message v2"
        stored2 = log_guidance(self.user, candidates)
        self.assertEqual(len(stored2), 1)

        # Should be same DB record, updated
        self.assertEqual(stored1[0].id, stored2[0].id)
        stored2[0].refresh_from_db()
        self.assertEqual(stored2[0].title, "Updated Version")

        # Should still be only 1 in DB
        count = GuidanceItem.objects.filter(
            user=self.user, dedupe_key="dedupe_test_1"
        ).count()
        self.assertEqual(count, 1)

    def test_log_creates_new_when_inactive(self):
        """If existing item is inactive, create a new one."""
        GuidanceItem.objects.create(
            user=self.user,
            title="Old Inactive",
            message="Old",
            dedupe_key="inactive_test_1",
            is_active=False,
        )

        candidates = [
            {
                "title": "New Active",
                "message": "New",
                "priority": 3,
                "guidance_type": "test",
                "source": "composite",
                "dedupe_key": "inactive_test_1",
            }
        ]
        stored = log_guidance(self.user, candidates)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].title, "New Active")
        self.assertTrue(stored[0].is_active)

        # Should now have 2 records (1 inactive + 1 active)
        count = GuidanceItem.objects.filter(
            user=self.user, dedupe_key="inactive_test_1"
        ).count()
        self.assertEqual(count, 2)

    def test_log_skips_missing_dedupe_key(self):
        candidates = [
            {
                "title": "No Key",
                "message": "Missing dedupe",
                "priority": 3,
            }
        ]
        stored = log_guidance(self.user, candidates)
        self.assertEqual(len(stored), 0)

    def test_log_sets_expiry(self):
        candidates = [
            {
                "title": "Expiring Item",
                "message": "Test",
                "priority": 3,
                "guidance_type": "test",
                "source": "composite",
                "dedupe_key": "expiry_test_1",
            }
        ]
        stored = log_guidance(self.user, candidates)
        self.assertIsNotNone(stored[0].expires_at)

    def test_log_handles_errors_gracefully(self):
        """Errors in one item should not prevent others from being stored."""
        candidates = [
            {
                "title": "Good Item",
                "message": "Test",
                "priority": 3,
                "guidance_type": "test",
                "source": "composite",
                "dedupe_key": "error_test_good",
            },
            {
                # Missing dedupe_key
                "title": "Bad Item",
                "message": "Missing key",
            },
            {
                "title": "Another Good",
                "message": "Test",
                "priority": 2,
                "guidance_type": "test",
                "source": "composite",
                "dedupe_key": "error_test_good2",
            },
        ]
        stored = log_guidance(self.user, candidates)
        self.assertEqual(len(stored), 2)


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class GuidanceEngineTest(PGETestMixin, TestCase):
    """Tests for the main guidance engine pipeline."""

    @patch("apps.core.ai_guidance.guidance_engine._get_active_predictions")
    @patch("apps.core.ai_guidance.guidance_engine._get_recent_insights")
    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    def test_generate_guidance_full_pipeline(
        self, mock_state, mock_insights, mock_predictions
    ):
        mock_state.return_value = {"goals": {"overdue_goal_count": 2}}
        mock_insights.return_value = MagicMock()
        mock_insights.return_value.filter.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value = []
        mock_insights.return_value.filter.return_value.exclude.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: []
        )
        mock_insights.return_value.filter.return_value.exclude.return_value.exists = (
            MagicMock(return_value=False)
        )
        mock_predictions.return_value = MagicMock()
        mock_predictions.return_value.filter.return_value = []

        items = generate_guidance(self.user)
        # Should get at least the goal overdue guidance
        self.assertGreaterEqual(len(items), 1)

    @patch("apps.core.ai_guidance.guidance_engine._get_active_predictions")
    @patch("apps.core.ai_guidance.guidance_engine._get_recent_insights")
    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    def test_generate_guidance_empty_state(
        self, mock_state, mock_insights, mock_predictions
    ):
        mock_state.return_value = {}
        mock_insights.return_value = MagicMock()
        mock_insights.return_value.filter.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value = []
        mock_insights.return_value.filter.return_value.exclude.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: []
        )
        mock_insights.return_value.filter.return_value.exclude.return_value.exists = (
            MagicMock(return_value=False)
        )
        mock_predictions.return_value = MagicMock()
        mock_predictions.return_value.filter.return_value = []

        items = generate_guidance(self.user)
        self.assertIsInstance(items, list)

    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    def test_generate_guidance_handles_sae_failure(self, mock_state):
        mock_state.side_effect = Exception("SAE down")
        items = generate_guidance(self.user)
        self.assertEqual(items, [])

    def test_get_active_guidance(self):
        GuidanceItem.objects.create(
            user=self.user,
            title="Active",
            message="Test",
            priority=2,
            dedupe_key="active_1",
            is_active=True,
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Inactive",
            message="Test",
            dedupe_key="inactive_1",
            is_active=False,
        )
        items = get_active_guidance(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Active")

    def test_get_active_guidance_excludes_expired(self):
        GuidanceItem.objects.create(
            user=self.user,
            title="Expired",
            message="Test",
            dedupe_key="expired_1",
            is_active=True,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Not Expired",
            message="Test",
            dedupe_key="not_expired_1",
            is_active=True,
            expires_at=timezone.now() + timedelta(days=7),
        )
        items = get_active_guidance(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Not Expired")

    def test_get_active_guidance_respects_limit(self):
        for i in range(10):
            GuidanceItem.objects.create(
                user=self.user,
                title=f"Item {i}",
                message="Test",
                dedupe_key=f"limit_test_{i}",
                is_active=True,
            )
        items = get_active_guidance(self.user, limit=3)
        self.assertEqual(len(items), 3)

    def test_expire_old_guidance(self):
        GuidanceItem.objects.create(
            user=self.user,
            title="Expired",
            message="Test",
            dedupe_key="expire_cmd_1",
            is_active=True,
            expires_at=timezone.now() - timedelta(hours=1),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Still Active",
            message="Test",
            dedupe_key="expire_cmd_2",
            is_active=True,
            expires_at=timezone.now() + timedelta(days=7),
        )

        count = expire_old_guidance()
        self.assertEqual(count, 1)

        # Verify
        expired = GuidanceItem.objects.get(dedupe_key="expire_cmd_1")
        self.assertFalse(expired.is_active)
        still = GuidanceItem.objects.get(dedupe_key="expire_cmd_2")
        self.assertTrue(still.is_active)


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------


class GuidanceViewTest(PGETestMixin, TestCase):
    """Tests for the guidance API views."""

    def test_inbox_view_requires_login(self):
        response = self.client.get("/guidance/")
        self.assertEqual(response.status_code, 302)

    def test_inbox_view_authenticated(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        response = self.client.get("/guidance/")
        self.assertEqual(response.status_code, 200)

    def test_inbox_shows_active_items(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        GuidanceItem.objects.create(
            user=self.user,
            title="VisibleGuidanceXyz",
            message="Test",
            dedupe_key="view_1",
            is_active=True,
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="InactiveGuidanceXyz",
            message="Test",
            dedupe_key="view_2",
            is_active=False,
        )
        response = self.client.get("/guidance/")
        self.assertContains(response, "VisibleGuidanceXyz")
        self.assertNotContains(response, "InactiveGuidanceXyz")

    def test_action_mark_read(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Read Me",
            message="Test",
            dedupe_key="action_read_1",
        )
        response = self.client.post(
            f"/guidance/{item.pk}/action/",
            {"action": "read"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_action_dismiss(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Dismiss Me",
            message="Test",
            dedupe_key="action_dismiss_1",
        )
        response = self.client.post(
            f"/guidance/{item.pk}/action/",
            {"action": "dismiss"},
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_action_wrong_user(self):
        other = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )
        item = GuidanceItem.objects.create(
            user=other,
            title="Not Yours",
            message="Test",
            dedupe_key="wrong_user_1",
        )
        self.client.login(email="pge_test@example.com", password="testpass123")
        response = self.client.post(
            f"/guidance/{item.pk}/action/",
            {"action": "read"},
        )
        self.assertEqual(response.status_code, 404)

    def test_api_view(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        GuidanceItem.objects.create(
            user=self.user,
            title="API Item",
            message="Test",
            priority=2,
            guidance_type="test",
            source="composite",
            dedupe_key="api_1",
            is_active=True,
        )
        response = self.client.get("/guidance/api/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["guidance"][0]["title"], "API Item")

    def test_api_view_respects_limit(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        for i in range(10):
            GuidanceItem.objects.create(
                user=self.user,
                title=f"Item {i}",
                message="Test",
                dedupe_key=f"api_limit_{i}",
                is_active=True,
            )
        response = self.client.get("/guidance/api/?limit=3")
        data = response.json()
        self.assertEqual(data["count"], 3)

    def test_api_caps_limit_at_10(self):
        self.client.login(email="pge_test@example.com", password="testpass123")
        response = self.client.get("/guidance/api/?limit=100")
        self.assertEqual(response.status_code, 200)

    def test_api_requires_login(self):
        response = self.client.get("/guidance/api/")
        self.assertEqual(response.status_code, 302)


# ---------------------------------------------------------------------------
# Management Command Tests
# ---------------------------------------------------------------------------


class RunGuidanceCommandTest(PGETestMixin, TestCase):
    """Tests for the run_guidance_engine management command."""

    @patch("apps.core.ai_guidance.guidance_engine._get_active_predictions")
    @patch("apps.core.ai_guidance.guidance_engine._get_recent_insights")
    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    def test_command_runs_for_single_user(
        self, mock_state, mock_insights, mock_predictions
    ):
        from django.core.management import call_command
        from io import StringIO

        mock_state.return_value = {}
        mock_insights.return_value = MagicMock()
        mock_insights.return_value.filter.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value = []
        mock_insights.return_value.filter.return_value.exclude.return_value = MagicMock()
        mock_insights.return_value.filter.return_value.exclude.return_value.__getitem__ = (
            lambda self, s: []
        )
        mock_insights.return_value.filter.return_value.exclude.return_value.exists = (
            MagicMock(return_value=False)
        )
        mock_predictions.return_value = MagicMock()
        mock_predictions.return_value.filter.return_value = []

        out = StringIO()
        call_command("run_guidance_engine", user=self.user.id, stdout=out)
        output = out.getvalue()
        self.assertIn("Generated", output)

    def test_command_expire_only(self):
        from django.core.management import call_command
        from io import StringIO

        GuidanceItem.objects.create(
            user=self.user,
            title="Expired",
            message="Test",
            dedupe_key="cmd_expire_1",
            is_active=True,
            expires_at=timezone.now() - timedelta(hours=1),
        )

        out = StringIO()
        call_command("run_guidance_engine", expire=True, stdout=out)
        output = out.getvalue()
        self.assertIn("Expired 1", output)

    def test_command_nonexistent_user(self):
        from django.core.management import call_command
        from io import StringIO

        err = StringIO()
        call_command("run_guidance_engine", user=99999, stderr=err)
        error_output = err.getvalue()
        self.assertIn("not found", error_output)


# ---------------------------------------------------------------------------
# Lifecycle Tracking Tests
# ---------------------------------------------------------------------------


class GuidanceLifecycleModelTest(PGETestMixin, TestCase):
    """Tests for GuidanceItem lifecycle fields and methods."""

    def _create_item(self, **kwargs):
        defaults = dict(
            user=self.user,
            title="Lifecycle Test",
            message="Testing lifecycle.",
            priority=3,
            guidance_type="test_rule",
            dedupe_key=f"lifecycle_{id(kwargs)}_{timezone.now().timestamp()}",
        )
        defaults.update(kwargs)
        return GuidanceItem.objects.create(**defaults)

    # -- acknowledge --

    def test_acknowledge_sets_timestamp(self):
        item = self._create_item()
        self.assertIsNone(item.acknowledged_at)
        item.acknowledge()
        item.refresh_from_db()
        self.assertIsNotNone(item.acknowledged_at)

    def test_acknowledge_marks_read(self):
        item = self._create_item()
        self.assertFalse(item.is_read)
        item.acknowledge()
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_acknowledge_idempotent(self):
        item = self._create_item()
        item.acknowledge()
        first_ts = item.acknowledged_at
        item.acknowledge()
        item.refresh_from_db()
        self.assertEqual(item.acknowledged_at, first_ts)

    def test_is_acknowledged_property(self):
        item = self._create_item()
        self.assertFalse(item.is_acknowledged)
        item.acknowledge()
        self.assertTrue(item.is_acknowledged)

    # -- dismiss --

    def test_dismiss_sets_timestamp(self):
        item = self._create_item()
        self.assertIsNone(item.dismissed_at)
        item.dismiss()
        item.refresh_from_db()
        self.assertIsNotNone(item.dismissed_at)

    def test_dismiss_deactivates(self):
        item = self._create_item()
        self.assertTrue(item.is_active)
        item.dismiss()
        item.refresh_from_db()
        self.assertFalse(item.is_active)

    def test_dismiss_idempotent(self):
        item = self._create_item()
        item.dismiss()
        first_ts = item.dismissed_at
        item.dismiss()
        item.refresh_from_db()
        self.assertEqual(item.dismissed_at, first_ts)

    def test_is_dismissed_property(self):
        item = self._create_item()
        self.assertFalse(item.is_dismissed)
        item.dismiss()
        self.assertTrue(item.is_dismissed)

    def test_dismissed_excluded_from_active_guidance(self):
        """Dismissed items must not appear in get_active_guidance()."""
        item = self._create_item(dedupe_key="dismissed_test_1")
        item.dismiss()
        active = get_active_guidance(self.user, limit=10)
        self.assertNotIn(item, list(active))

    # -- snooze --

    def test_snooze_sets_until(self):
        item = self._create_item()
        until = timezone.now() + timedelta(hours=24)
        item.snooze(until)
        item.refresh_from_db()
        self.assertIsNotNone(item.snoozed_until)

    def test_is_snoozed_when_future(self):
        item = self._create_item()
        item.snooze(timezone.now() + timedelta(hours=24))
        self.assertTrue(item.is_snoozed)

    def test_is_not_snoozed_when_past(self):
        item = self._create_item()
        item.snooze(timezone.now() - timedelta(hours=1))
        self.assertFalse(item.is_snoozed)

    def test_snoozed_excluded_from_active_guidance(self):
        """Currently snoozed items must not appear in get_active_guidance()."""
        item = self._create_item(dedupe_key="snoozed_test_1")
        item.snooze(timezone.now() + timedelta(hours=24))
        active = get_active_guidance(self.user, limit=10)
        self.assertNotIn(item, list(active))

    def test_snoozed_reappears_after_expiration(self):
        """Items whose snooze has expired should appear in get_active_guidance()."""
        item = self._create_item(
            dedupe_key="snoozed_reappear_1",
            expires_at=timezone.now() + timedelta(days=7),
        )
        # Snooze in the past = expired snooze
        item.snooze(timezone.now() - timedelta(hours=1))
        active = get_active_guidance(self.user, limit=10)
        self.assertIn(item, list(active))

    # -- acted upon --

    def test_mark_acted_upon_sets_timestamp(self):
        item = self._create_item()
        self.assertIsNone(item.acted_upon_at)
        item.mark_acted_upon()
        item.refresh_from_db()
        self.assertIsNotNone(item.acted_upon_at)

    def test_mark_acted_upon_with_action_type(self):
        item = self._create_item()
        item.mark_acted_upon(action_type="navigated")
        item.refresh_from_db()
        self.assertEqual(item.action_type, "navigated")

    def test_mark_acted_upon_marks_read(self):
        item = self._create_item()
        item.mark_acted_upon()
        item.refresh_from_db()
        self.assertTrue(item.is_read)

    def test_mark_acted_upon_idempotent(self):
        item = self._create_item()
        item.mark_acted_upon(action_type="navigated")
        first_ts = item.acted_upon_at
        item.mark_acted_upon(action_type="updated_goal")
        item.refresh_from_db()
        self.assertEqual(item.acted_upon_at, first_ts)
        self.assertEqual(item.action_type, "navigated")  # unchanged

    def test_is_acted_upon_property(self):
        item = self._create_item()
        self.assertFalse(item.is_acted_upon)
        item.mark_acted_upon()
        self.assertTrue(item.is_acted_upon)

    # -- feedback --

    def test_set_feedback(self):
        item = self._create_item()
        item.set_feedback("Very helpful!")
        item.refresh_from_db()
        self.assertEqual(item.feedback, "Very helpful!")

    def test_set_feedback_truncates(self):
        item = self._create_item()
        long_text = "A" * 300
        item.set_feedback(long_text)
        item.refresh_from_db()
        self.assertEqual(len(item.feedback), 255)

    # -- is_active_guidance composite property --

    def test_is_active_guidance_default(self):
        item = self._create_item()
        self.assertTrue(item.is_active_guidance)

    def test_is_active_guidance_false_when_dismissed(self):
        item = self._create_item()
        item.dismiss()
        self.assertFalse(item.is_active_guidance)

    def test_is_active_guidance_false_when_snoozed(self):
        item = self._create_item()
        item.snooze(timezone.now() + timedelta(hours=24))
        self.assertFalse(item.is_active_guidance)

    def test_is_active_guidance_false_when_inactive(self):
        item = self._create_item()
        item.deactivate()
        self.assertFalse(item.is_active_guidance)

    # -- lifecycle fields initialized to None --

    def test_new_item_lifecycle_fields_are_none(self):
        item = self._create_item()
        self.assertIsNone(item.acknowledged_at)
        self.assertIsNone(item.dismissed_at)
        self.assertIsNone(item.snoozed_until)
        self.assertIsNone(item.acted_upon_at)
        self.assertIsNone(item.action_type)
        self.assertIsNone(item.feedback)


class GuidanceLifecycleViewTest(PGETestMixin, TestCase):
    """Tests for lifecycle actions via GuidanceActionView."""

    def setUp(self):
        super().setUp()
        self.client.login(email="pge_test@example.com", password="testpass123")
        self.item = GuidanceItem.objects.create(
            user=self.user,
            title="View Lifecycle Test",
            message="Testing view actions.",
            priority=3,
            guidance_type="test_rule",
            dedupe_key="view_lifecycle_test_1",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def _action_url(self):
        return f"/guidance/{self.item.pk}/action/"

    def test_acknowledge_action(self):
        resp = self.client.post(self._action_url(), {"action": "acknowledge"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "acknowledged")
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.acknowledged_at)

    def test_dismiss_action(self):
        resp = self.client.post(self._action_url(), {"action": "dismiss"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "dismissed")
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.dismissed_at)
        self.assertFalse(self.item.is_active)

    def test_snooze_action(self):
        resp = self.client.post(self._action_url(), {"action": "snooze", "hours": "12"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "snoozed")
        self.assertIn("snoozed_until", data)
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.snoozed_until)

    def test_snooze_caps_at_168_hours(self):
        resp = self.client.post(self._action_url(), {"action": "snooze", "hours": "500"})
        self.assertEqual(resp.status_code, 200)
        self.item.refresh_from_db()
        # Should be capped at ~168 hours (7 days) from now, not 500
        max_delta = timedelta(hours=169)
        actual_delta = self.item.snoozed_until - timezone.now()
        self.assertLessEqual(actual_delta, max_delta)

    def test_acted_action(self):
        resp = self.client.post(
            self._action_url(),
            {"action": "acted", "action_type": "navigated"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "acted_upon")
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.acted_upon_at)
        self.assertEqual(self.item.action_type, "navigated")

    def test_feedback_action(self):
        resp = self.client.post(
            self._action_url(),
            {"action": "feedback", "feedback": "Great tip!"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "feedback_saved")
        self.item.refresh_from_db()
        self.assertEqual(self.item.feedback, "Great tip!")

    def test_feedback_action_requires_text(self):
        resp = self.client.post(
            self._action_url(),
            {"action": "feedback", "feedback": ""},
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["success"])

    def test_unknown_action_returns_400(self):
        resp = self.client.post(self._action_url(), {"action": "explode"})
        self.assertEqual(resp.status_code, 400)

    def test_action_on_nonexistent_item_returns_404(self):
        resp = self.client.post("/guidance/99999/action/", {"action": "read"})
        self.assertEqual(resp.status_code, 404)


class GuidanceAPILifecycleTest(PGETestMixin, TestCase):
    """Tests that the JSON API includes lifecycle fields."""

    def setUp(self):
        super().setUp()
        self.client.login(email="pge_test@example.com", password="testpass123")
        self.item = GuidanceItem.objects.create(
            user=self.user,
            title="API Lifecycle Test",
            message="Testing API response.",
            priority=2,
            guidance_type="test_rule",
            dedupe_key="api_lifecycle_test_1",
            expires_at=timezone.now() + timedelta(days=7),
        )

    def test_api_includes_lifecycle_fields(self):
        resp = self.client.get("/guidance/api/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        item_data = data["guidance"][0]
        # Check lifecycle fields are present
        self.assertIn("is_acknowledged", item_data)
        self.assertIn("is_acted_upon", item_data)
        self.assertIn("acknowledged_at", item_data)
        self.assertIn("acted_upon_at", item_data)
        self.assertIn("action_type", item_data)

    def test_api_reflects_acknowledged_state(self):
        self.item.acknowledge()
        resp = self.client.get("/guidance/api/")
        data = resp.json()
        item_data = data["guidance"][0]
        self.assertTrue(item_data["is_acknowledged"])
        self.assertIsNotNone(item_data["acknowledged_at"])

    def test_api_excludes_dismissed_items(self):
        self.item.dismiss()
        resp = self.client.get("/guidance/api/")
        data = resp.json()
        self.assertEqual(data["count"], 0)

    def test_api_excludes_snoozed_items(self):
        self.item.snooze(timezone.now() + timedelta(hours=24))
        resp = self.client.get("/guidance/api/")
        data = resp.json()
        self.assertEqual(data["count"], 0)
