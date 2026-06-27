"""
Tests — PIE event subscribers route health writes into run_insights().

Regression coverage for the 2026-06-27 silent-failure bug: the
health.medication.taken / health.weight.logged / health.sleep.logged
subscribers called per-domain check_*_insights() helpers that no longer
exist. The resulting ImportError was swallowed by `except ImportError: pass`,
so dashboard/web dose, weight, and sleep logging fired NO PIE pass at all.

These tests assert the subscribers now invoke run_insights() with a proper
health event dict, and that the real rule set actually runs for the event.

Path: apps/core/events/tests/test_pie_subscribers.py
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.events.domain_events import emit_event

User = get_user_model()


class HealthPIESubscriberTests(TestCase):
    """Emitting health.* events must drive the run_insights() PIE entry point."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="pie-subscriber@example.com", password="x"
        )

    def _assert_runs_pie(self, event_type, expected_action):
        # Patch run_insights in the subscriber's import target so we capture
        # the exact event dict the handler builds.
        with patch(
            "apps.core.ai_insights.insight_engine.run_insights"
        ) as mock_run:
            emit_event(event_type, user=self.user, data={"entry_id": 12345})

        self.assertTrue(
            mock_run.called,
            f"{event_type} did not invoke run_insights() — PIE pass skipped",
        )
        called_user, called_event = mock_run.call_args[0]
        self.assertEqual(called_user, self.user)
        self.assertEqual(called_event["event_type"], "record_created")
        self.assertEqual(called_event["module"], "health")
        self.assertEqual(called_event["action"], expected_action)
        self.assertIn("timestamp_utc", called_event)

    def test_medication_taken_runs_pie(self):
        self._assert_runs_pie("health.medication.taken", "log_medication")

    def test_weight_logged_runs_pie(self):
        self._assert_runs_pie("health.weight.logged", "log_weight")

    def test_sleep_logged_runs_pie(self):
        self._assert_runs_pie("health.sleep.logged", "log_sleep")

    def test_medication_event_executes_real_rule_set(self):
        """End-to-end: emitting the event runs the actual PIE rules.

        We don't assert a specific Insight is created (that needs domain
        data); we assert the rule pipeline is exercised — i.e. at least one
        registered rule's applies() is consulted for the medication event.
        This proves the subscriber reaches the rules, not just a mock.
        """
        from apps.core.ai_insights.rule_registry import get_rules

        # run_insights auto-registers rules on import; confirm the registry
        # is populated so the pass below is meaningful.
        self.assertTrue(get_rules(), "No PIE rules registered")

        seen = {}

        original_applies = None
        # Spy on a health rule's applies() to confirm the event reaches it.
        from apps.core.ai_insights.rules_transformation import (  # noqa: E501
            FastingConsistencyRule,
        )
        original_applies = FastingConsistencyRule.applies

        def spy_applies(self_rule, user, event):
            seen["event"] = event
            return original_applies(self_rule, user, event)

        with patch.object(FastingConsistencyRule, "applies", spy_applies):
            emit_event(
                "health.medication.taken",
                user=self.user,
                data={"entry_id": 999},
            )

        self.assertIn(
            "event", seen, "Medication event never reached the PIE rule set"
        )
        self.assertEqual(seen["event"]["module"], "health")
        self.assertEqual(seen["event"]["action"], "log_medication")

    def test_import_failure_is_logged_not_swallowed(self):
        """A missing PIE entry point must be logged, never silently passed.

        This is the core-rule guard: the original bug was an ImportError
        swallowed by `except ImportError: pass`. The handler now logs it.
        """
        from apps.core.events import subscribers

        with patch.dict(
            "sys.modules", {"apps.core.ai_insights.insight_engine": None}
        ):
            with self.assertLogs(subscribers.logger, level="WARNING") as cm:
                subscribers._run_health_pie(self.user, "log_medication")

        self.assertTrue(
            any("PIE entry point unavailable" in m for m in cm.output),
            "ImportError was swallowed instead of logged",
        )
