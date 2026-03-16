"""
Test suite for Proactive Insight Engine (PIE).
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.insight_engine import _upsert_insight, run_insights
from apps.core.ai_insights.models import Insight, build_dedupe_key
from apps.core.ai_insights.notification_engine import maybe_notify
from apps.core.ai_insights.pattern_utils import (
    compute_simple_trend,
    days_since,
    get_time_window,
    percent_change,
    requires_min_points,
)
from apps.core.ai_insights.rule_registry import RULES, get_rules, register
from apps.users.models import User


class PIETestMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            email="pietest@example.com", password="testpass123"
        )


# ─── Model Tests ───


class InsightModelTests(PIETestMixin, TestCase):
    def test_create_insight(self):
        insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="weight_trend_up",
            severity="warning",
            title="Weight trending up",
            message="Your weight increased.",
            confidence_score=0.85,
            explain_why="14-day trend analysis",
            evidence={"record_ids": [1, 2, 3]},
            dedupe_key="test_key_123",
        )
        self.assertEqual(insight.status, "new")
        self.assertIsNotNone(insight.created_at)

    def test_str_representation(self):
        insight = Insight(severity="warning", title="Test insight")
        self.assertIn("warning", str(insight))
        self.assertIn("Test insight", str(insight))


class DedupeKeyTests(TestCase):
    def test_same_inputs_same_key(self):
        key1 = build_dedupe_key(1, "weight_trend_up", "2026-02-01", "2026-02-14")
        key2 = build_dedupe_key(1, "weight_trend_up", "2026-02-01", "2026-02-14")
        self.assertEqual(key1, key2)

    def test_different_user_different_key(self):
        key1 = build_dedupe_key(1, "weight_trend_up", "2026-02-01", "2026-02-14")
        key2 = build_dedupe_key(2, "weight_trend_up", "2026-02-01", "2026-02-14")
        self.assertNotEqual(key1, key2)

    def test_different_type_different_key(self):
        key1 = build_dedupe_key(1, "weight_trend_up", "2026-02-01", "2026-02-14")
        key2 = build_dedupe_key(1, "weight_trend_down", "2026-02-01", "2026-02-14")
        self.assertNotEqual(key1, key2)

    def test_with_record_ids(self):
        key1 = build_dedupe_key(1, "test", "a", "b", [1, 2, 3])
        key2 = build_dedupe_key(1, "test", "a", "b", [3, 2, 1])  # Different order
        self.assertEqual(key1, key2)  # Should normalize order


# ─── Pattern Utils Tests ───


class PatternUtilsTests(TestCase):
    def test_get_time_window(self):
        start, end = get_time_window(days=14)
        self.assertTrue(start < end)
        self.assertAlmostEqual((end - start).days, 14, delta=1)

    def test_compute_trend_up(self):
        data = [
            (date(2026, 2, 1), 200),
            (date(2026, 2, 7), 205),
            (date(2026, 2, 14), 210),
        ]
        trend = compute_simple_trend(data)
        self.assertEqual(trend["direction"], "up")
        self.assertEqual(trend["net_change"], 10)

    def test_compute_trend_down(self):
        data = [
            (date(2026, 2, 1), 210),
            (date(2026, 2, 7), 205),
            (date(2026, 2, 14), 200),
        ]
        trend = compute_simple_trend(data)
        self.assertEqual(trend["direction"], "down")
        self.assertEqual(trend["net_change"], -10)

    def test_compute_trend_flat(self):
        data = [
            (date(2026, 2, 1), 200),
            (date(2026, 2, 14), 200),
        ]
        trend = compute_simple_trend(data)
        self.assertEqual(trend["direction"], "flat")

    def test_compute_trend_insufficient_data(self):
        data = [(date(2026, 2, 1), 200)]
        self.assertIsNone(compute_simple_trend(data))

    def test_percent_change(self):
        self.assertEqual(percent_change(100, 110), 10.0)
        self.assertEqual(percent_change(100, 90), -10.0)

    def test_requires_min_points(self):
        self.assertTrue(requires_min_points([1, 2, 3], 3))
        self.assertFalse(requires_min_points([1, 2], 3))


# ─── Insight Engine Tests ───


class InsightEngineTests(PIETestMixin, TestCase):
    def test_upsert_creates_new(self):
        class MockRule:
            module = "health"
            insight_type = "test_type"

        insight_data = {
            "severity": "info",
            "title": "Test",
            "message": "Test message",
            "confidence_score": 0.8,
            "explain_why": "Test reason",
            "evidence": {},
            "dedupe_key": "unique_key_1",
        }
        result = _upsert_insight(self.user, MockRule(), insight_data)
        self.assertIsNotNone(result)
        self.assertEqual(result.title, "Test")

    def test_upsert_deduplicates(self):
        class MockRule:
            module = "health"
            insight_type = "test_type"

        insight_data = {
            "severity": "info",
            "title": "Test",
            "message": "Original message",
            "confidence_score": 0.8,
            "explain_why": "Test",
            "evidence": {},
            "dedupe_key": "same_key",
        }
        _upsert_insight(self.user, MockRule(), insight_data)

        # Same key — should update, not create new
        insight_data["message"] = "Updated message"
        _upsert_insight(self.user, MockRule(), insight_data)

        count = Insight.objects.filter(user=self.user, dedupe_key="same_key").count()
        self.assertEqual(count, 1)

        insight = Insight.objects.get(user=self.user, dedupe_key="same_key")
        self.assertEqual(insight.message, "Updated message")

    def test_dismissed_insight_not_updated(self):
        class MockRule:
            module = "health"
            insight_type = "test_type"

        insight_data = {
            "severity": "info",
            "title": "Test",
            "message": "Original",
            "confidence_score": 0.8,
            "explain_why": "Test",
            "evidence": {},
            "dedupe_key": "dismissed_key",
        }
        insight = _upsert_insight(self.user, MockRule(), insight_data)
        insight.status = "dismissed"
        insight.save()

        # New insight with same key should create new (dismissed != blocked)
        insight_data["message"] = "New insight"
        result = _upsert_insight(self.user, MockRule(), insight_data)
        self.assertEqual(result.message, "New insight")
        self.assertEqual(
            Insight.objects.filter(user=self.user, dedupe_key="dismissed_key").count(),
            2,
        )


# ─── Weight Rule Tests ───


class WeightTrendUpRuleTests(PIETestMixin, TestCase):
    def test_triggers_with_sufficient_data(self):
        from apps.health.models import WeightEntry

        # Create 4 weight entries trending up by > 5 lbs
        now = timezone.now()
        for i, val in enumerate([250, 252, 255, 258]):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(val)),
                unit="lb",
                recorded_at=now - timedelta(days=12 - i * 3),
            )

        from apps.core.ai_insights.rules_health import WeightTrendUpRule

        rule = WeightTrendUpRule()
        event = {"module": "health", "action": "log_weight"}
        self.assertTrue(rule.applies(self.user, event))

        insights = rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")
        self.assertIn("record_ids", insights[0]["evidence"])

    def test_does_not_trigger_with_insufficient_data(self):
        from apps.health.models import WeightEntry

        # Only 1 entry — below minimum of 2
        now = timezone.now()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("250"), unit="lb",
            recorded_at=now - timedelta(days=10),
        )

        from apps.core.ai_insights.rules_health import WeightTrendUpRule

        rule = WeightTrendUpRule()
        insights = rule.evaluate(self.user, {"module": "health", "action": "log_weight"})
        self.assertEqual(len(insights), 0)

    def test_does_not_trigger_when_change_zero(self):
        from apps.health.models import WeightEntry

        now = timezone.now()
        for i, val in enumerate([250, 250, 250]):
            WeightEntry.objects.create(
                user=self.user, value=Decimal(str(val)), unit="lb",
                recorded_at=now - timedelta(days=10 - i * 3),
            )

        from apps.core.ai_insights.rules_health import WeightTrendUpRule

        rule = WeightTrendUpRule()
        insights = rule.evaluate(self.user, {"module": "health", "action": "log_weight"})
        self.assertEqual(len(insights), 0)  # No change — flat trend


class MissingWeightRuleTests(PIETestMixin, TestCase):
    def test_triggers_when_gap_exceeds_threshold(self):
        from apps.health.models import WeightEntry

        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("250"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=20),
        )

        from apps.core.ai_insights.rules_health import MissingWeightLoggingRule

        rule = MissingWeightLoggingRule()
        insights = rule.evaluate(self.user, {"event_type": "scheduled_check"})
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "info")

    def test_does_not_trigger_when_recent(self):
        from apps.health.models import WeightEntry

        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("250"),
            unit="lb",
            recorded_at=timezone.now() - timedelta(days=2),
        )

        from apps.core.ai_insights.rules_health import MissingWeightLoggingRule

        rule = MissingWeightLoggingRule()
        insights = rule.evaluate(self.user, {"event_type": "scheduled_check"})
        self.assertEqual(len(insights), 0)


# ─── Goal Rule Tests ───


class GoalDeadlineRiskRuleTests(PIETestMixin, TestCase):
    def test_triggers_for_approaching_deadline(self):
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title="Test Goal",
            target_date=date.today() + timedelta(days=15),
            status="active",
        )

        from apps.core.ai_insights.rules_goals import GoalDeadlineRiskRule

        rule = GoalDeadlineRiskRule()
        insights = rule.evaluate(
            self.user, {"module": "purpose", "event_type": "scheduled_check"}
        )
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")

    def test_does_not_trigger_for_distant_deadline(self):
        from apps.purpose.models import LifeGoal

        LifeGoal.objects.create(
            user=self.user,
            title="Far Goal",
            target_date=date.today() + timedelta(days=90),
            status="active",
        )

        from apps.core.ai_insights.rules_goals import GoalDeadlineRiskRule

        rule = GoalDeadlineRiskRule()
        insights = rule.evaluate(
            self.user, {"module": "purpose", "event_type": "scheduled_check"}
        )
        self.assertEqual(len(insights), 0)


# ─── Goal Progress Rule Tests ───


class GoalProgressRuleTests(PIETestMixin, TestCase):
    """Test GoalProgressRule — milestone and goal completion insights."""

    def test_applies_on_complete_milestone(self):
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        self.assertTrue(rule.applies(self.user, {
            "module": "purpose", "action": "complete_milestone",
        }))

    def test_applies_on_complete_goal(self):
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        self.assertTrue(rule.applies(self.user, {
            "module": "purpose", "action": "complete_goal",
        }))

    def test_does_not_apply_on_other_actions(self):
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        self.assertFalse(rule.applies(self.user, {
            "module": "purpose", "action": "record_created",
        }))

    def test_does_not_apply_on_wrong_module(self):
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        self.assertFalse(rule.applies(self.user, {
            "module": "health", "action": "complete_milestone",
        }))

    def test_milestone_completion_produces_insight(self):
        from apps.purpose.models import GoalMilestone, LifeGoal
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        goal = LifeGoal.objects.create(
            user=self.user, title="Test Goal", status="active",
        )
        m1 = GoalMilestone.objects.create(goal=goal, title="Step 1", completed=True)
        GoalMilestone.objects.create(goal=goal, title="Step 2", completed=False)

        rule = GoalProgressRule()
        insights = rule.evaluate(self.user, {
            "module": "purpose",
            "action": "complete_milestone",
            "record_id": m1.id,
        })
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "positive")
        self.assertIn("Step 1", insights[0]["title"])
        self.assertEqual(insights[0]["evidence"]["progress_pct"], 50)

    def test_goal_completion_produces_insight(self):
        from apps.purpose.models import LifeGoal
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        goal = LifeGoal.objects.create(
            user=self.user, title="Completed Goal", status="completed",
        )

        rule = GoalProgressRule()
        insights = rule.evaluate(self.user, {
            "module": "purpose",
            "action": "complete_goal",
            "record_id": goal.id,
        })
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "positive")
        self.assertIn("Completed Goal", insights[0]["title"])

    def test_milestone_not_found_returns_empty(self):
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        insights = rule.evaluate(self.user, {
            "module": "purpose",
            "action": "complete_milestone",
            "record_id": 99999,
        })
        self.assertEqual(len(insights), 0)

    def test_module_is_purpose(self):
        """GoalProgressRule.module should be 'purpose' for signal pipeline."""
        from apps.core.ai_insights.rules_goals import GoalProgressRule

        rule = GoalProgressRule()
        self.assertEqual(rule.module, "purpose")


# ─── Notification Engine Tests ───


class NotificationEngineTests(PIETestMixin, TestCase):
    def test_notifies_on_warning(self):
        insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="test",
            severity="warning",
            title="Test",
            message="Test",
            confidence_score=0.85,
            explain_why="Test",
            dedupe_key="notify_test_1",
        )
        result = maybe_notify(self.user, insight)
        self.assertTrue(result)
        insight.refresh_from_db()
        self.assertIsNotNone(insight.notified_at)

    def test_does_not_notify_on_info(self):
        insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="test",
            severity="info",
            title="Test",
            message="Test",
            confidence_score=0.85,
            explain_why="Test",
            dedupe_key="notify_test_2",
        )
        result = maybe_notify(self.user, insight)
        self.assertFalse(result)

    def test_rate_limiting(self):
        # Create 3 already-notified insights today
        for i in range(3):
            Insight.objects.create(
                user=self.user,
                module="health",
                insight_type="test",
                severity="warning",
                title=f"Test {i}",
                message="Test",
                confidence_score=0.85,
                explain_why="Test",
                dedupe_key=f"rate_limit_{i}",
                notified_at=timezone.now(),
            )

        # 4th should be rate-limited
        new_insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="test",
            severity="warning",
            title="Test 4",
            message="Test",
            confidence_score=0.85,
            explain_why="Test",
            dedupe_key="rate_limit_4",
        )
        result = maybe_notify(self.user, new_insight)
        self.assertFalse(result)


# ─── Rule Registry Tests ───


class RuleRegistryTests(TestCase):
    def test_rules_registered(self):
        # Import rule modules to trigger registration
        import apps.core.ai_insights.rules_health  # noqa: F401
        import apps.core.ai_insights.rules_goals  # noqa: F401

        rules = get_rules()
        self.assertTrue(len(rules) > 0)

    def test_all_rules_have_required_attrs(self):
        import apps.core.ai_insights.rules_health  # noqa: F401

        for rule in get_rules():
            self.assertTrue(hasattr(rule, "rule_name"))
            self.assertTrue(hasattr(rule, "module"))
            self.assertTrue(hasattr(rule, "insight_type"))
            self.assertTrue(hasattr(rule, "applies"))
            self.assertTrue(hasattr(rule, "evaluate"))


# ─── Views Tests ───


class InsightsInboxViewTests(PIETestMixin, TestCase):
    def test_inbox_requires_login(self):
        response = self.client.get("/insights/")
        self.assertEqual(response.status_code, 302)

    def test_inbox_loads(self):
        from apps.users.models import TermsAcceptance
        from django.conf import settings

        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.client.login(email="pietest@example.com", password="testpass123")
        response = self.client.get("/insights/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insights")
