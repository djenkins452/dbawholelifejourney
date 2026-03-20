"""
Tests for the AI Action Failure Rate (AAFR) telemetry system.

Tests cover:
  - AIActionMetric model (all three outcome types)
  - _record_aafr() helper resilience
  - execute_action() hook integration (all 5 exit paths)
  - _get_aafr_metrics() aggregation & status thresholds
  - OpsStreamView 'aafr' key presence
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from apps.core.ai_observability.models import AIActionMetric


class AIActionMetricModelTests(TestCase):
    """Basic model tests for AIActionMetric."""

    def test_create_success(self):
        m = AIActionMetric.objects.create(
            intent_type="create_task",
            outcome="success",
            duration_ms=42,
            user_id=1,
        )
        self.assertEqual(m.outcome, "success")
        self.assertEqual(m.error_category, "")
        self.assertIn("create_task", str(m))
        self.assertIn("[success]", str(m))

    def test_create_blocked(self):
        m = AIActionMetric.objects.create(
            intent_type="delete_task",
            outcome="blocked",
            error_category="safety_blocked",
            duration_ms=3,
            user_id=1,
        )
        self.assertEqual(m.outcome, "blocked")
        self.assertEqual(m.error_category, "safety_blocked")

    def test_create_failure(self):
        m = AIActionMetric.objects.create(
            intent_type="log_weight",
            outcome="failure",
            error_category="internal_error",
            duration_ms=150,
            user_id=1,
        )
        self.assertEqual(m.outcome, "failure")
        self.assertIn("[failure]", str(m))

    def test_ordering_newest_first(self):
        AIActionMetric.objects.create(intent_type="a", outcome="success")
        AIActionMetric.objects.create(intent_type="b", outcome="success")
        first = AIActionMetric.objects.first()
        self.assertEqual(first.intent_type, "b")


class RecordAAFRHelperTests(TestCase):
    """Tests for the _record_aafr() helper — must never raise."""

    def test_records_metric(self):
        import time
        from apps.core.ai_orchestrator.execution_engine import _record_aafr

        user = MagicMock(id=42)
        start = time.monotonic() - 0.05  # 50ms ago
        _record_aafr(user, "create_task", "success", "", start)

        self.assertEqual(AIActionMetric.objects.count(), 1)
        m = AIActionMetric.objects.first()
        self.assertEqual(m.intent_type, "create_task")
        self.assertEqual(m.outcome, "success")
        self.assertEqual(m.user_id, 42)
        self.assertGreaterEqual(m.duration_ms, 1)

    @patch("apps.core.ai_observability.models.AIActionMetric.objects")
    def test_never_raises_on_db_error(self, mock_objects):
        """Telemetry recording must not block execution."""
        from apps.core.ai_orchestrator.execution_engine import _record_aafr

        mock_objects.create.side_effect = Exception("DB down")
        # Should not raise
        _record_aafr(MagicMock(id=1), "create_task", "success")


class ExecuteActionHookTests(TestCase):
    """Integration tests: execute_action() records AAFR for all 5 exit paths."""

    def _make_enriched_action(self, intent_type="create_task"):
        ea = MagicMock()
        ea.intent_type = intent_type
        ea.parameters = {"title": "Test"}
        return ea

    @patch("apps.core.ai_orchestrator.execution_engine.validate_action")
    @patch("apps.core.blueprint.learning_mode.is_learning_mode_active", return_value=True)
    def test_learning_mode_blocked_records_blocked(self, mock_lm, mock_safety):
        from apps.core.ai_orchestrator.execution_engine import execute_action

        user = MagicMock(id=1)
        result = execute_action(user, self._make_enriched_action())

        self.assertFalse(result.success)
        m = AIActionMetric.objects.filter(outcome="blocked").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.error_category, "learning_mode_active")

    @patch("apps.core.ai_orchestrator.execution_engine.validate_action")
    @patch("apps.core.blueprint.learning_mode.is_learning_mode_active", side_effect=RuntimeError("crash"))
    def test_lm_check_crash_records_failure(self, mock_lm, mock_safety):
        from apps.core.ai_orchestrator.execution_engine import execute_action

        user = MagicMock(id=1)
        result = execute_action(user, self._make_enriched_action())

        self.assertFalse(result.success)
        m = AIActionMetric.objects.filter(outcome="failure").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.error_category, "learning_mode_check_failed")

    @patch("apps.core.blueprint.learning_mode.is_learning_mode_active", return_value=False)
    @patch("apps.ai.intent_service.intent_service")
    @patch("apps.core.ai_orchestrator.execution_engine.validate_action")
    def test_safety_blocked_records_blocked(self, mock_safety, mock_is, mock_lm):
        mock_safety.return_value = MagicMock(
            is_safe=False, reason="destructive_action", user_message="Blocked."
        )
        from apps.core.ai_orchestrator.execution_engine import execute_action

        user = MagicMock(id=1)
        result = execute_action(user, self._make_enriched_action())

        self.assertFalse(result.success)
        m = AIActionMetric.objects.filter(outcome="blocked").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.error_category, "safety_blocked")

    @patch("apps.core.blueprint.learning_mode.is_learning_mode_active", return_value=False)
    @patch("apps.core.ai_orchestrator.execution_engine.validate_action")
    def test_handler_exception_records_failure(self, mock_safety, mock_lm):
        mock_safety.return_value = MagicMock(is_safe=True)
        with patch("apps.ai.intent_service.intent_service") as mock_is:
            mock_is.execute_intent.side_effect = RuntimeError("handler boom")
            from apps.core.ai_orchestrator.execution_engine import execute_action

            user = MagicMock(id=1)
            result = execute_action(user, self._make_enriched_action())

        self.assertFalse(result.success)
        m = AIActionMetric.objects.filter(outcome="failure").first()
        self.assertIsNotNone(m)
        self.assertEqual(m.error_category, "internal_error")

    @patch("apps.core.blueprint.learning_mode.is_learning_mode_active", return_value=False)
    @patch("apps.core.ai_orchestrator.execution_engine.validate_action")
    def test_success_records_success(self, mock_safety, mock_lm):
        mock_safety.return_value = MagicMock(is_safe=True)
        from apps.ai.intent_service import ActionResult

        success_result = ActionResult(
            success=True, message="Done", action_type="create_task"
        )
        with patch("apps.ai.intent_service.intent_service") as mock_is:
            mock_is.execute_intent.return_value = success_result
            from apps.core.ai_orchestrator.execution_engine import execute_action

            user = MagicMock(id=1)
            result = execute_action(user, self._make_enriched_action())

        self.assertTrue(result.success)
        m = AIActionMetric.objects.filter(outcome="success").first()
        self.assertIsNotNone(m)


class AAFRAggregationTests(TestCase):
    """Tests for _get_aafr_metrics() aggregation and status thresholds."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def _create_metrics(self, outcome, count, age_minutes=0):
        """Create count metrics with given outcome, aged back by age_minutes."""
        now = timezone.now()
        for _ in range(count):
            m = AIActionMetric.objects.create(
                intent_type="test_action",
                outcome=outcome,
            )
            if age_minutes > 0:
                AIActionMetric.objects.filter(pk=m.pk).update(
                    created_at=now - timedelta(minutes=age_minutes)
                )

    def test_all_success_returns_healthy(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        self._create_metrics("success", 10)
        result = _get_aafr_metrics()

        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["1h"]["success_rate"], 100.0)
        self.assertEqual(result["1h"]["failed"], 0)

    def test_failure_rate_warning_threshold(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        # 98 success + 2 failure = 2% failure rate
        self._create_metrics("success", 98)
        self._create_metrics("failure", 2)
        result = _get_aafr_metrics()

        self.assertEqual(result["status"], "WARNING")
        self.assertGreaterEqual(result["1h"]["failure_rate"], 1.0)

    def test_failure_rate_critical_threshold(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        # 90 success + 10 failure = 10% failure rate
        self._create_metrics("success", 90)
        self._create_metrics("failure", 10)
        result = _get_aafr_metrics()

        self.assertEqual(result["status"], "CRITICAL")
        self.assertGreaterEqual(result["1h"]["failure_rate"], 3.0)

    def test_blocked_does_not_affect_failure_rate(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        # 90 success + 10 blocked + 0 failure = 0% failure rate
        self._create_metrics("success", 90)
        self._create_metrics("blocked", 10)
        result = _get_aafr_metrics()

        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["1h"]["failure_rate"], 0.0)
        self.assertEqual(result["1h"]["blocked"], 10)

    def test_time_window_filtering(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        # 5 recent successes + 5 old failures (>1h ago)
        self._create_metrics("success", 5)
        self._create_metrics("failure", 5, age_minutes=120)
        result = _get_aafr_metrics()

        # 1h window should only see 5 successes
        self.assertEqual(result["1h"]["total"], 5)
        self.assertEqual(result["1h"]["failed"], 0)
        self.assertEqual(result["status"], "HEALTHY")

        # 24h window should see all 10
        self.assertEqual(result["24h"]["total"], 10)
        self.assertEqual(result["24h"]["failed"], 5)

    def test_top_errors_populated(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        for _ in range(3):
            AIActionMetric.objects.create(
                intent_type="t", outcome="failure", error_category="internal_error"
            )
        for _ in range(2):
            AIActionMetric.objects.create(
                intent_type="t", outcome="failure", error_category="safety_blocked"
            )
        result = _get_aafr_metrics()

        self.assertEqual(len(result["top_errors"]), 2)
        self.assertEqual(result["top_errors"][0]["category"], "internal_error")
        self.assertEqual(result["top_errors"][0]["count"], 3)

    def test_empty_table_returns_healthy(self):
        from apps.core.ai_observability.ops_views import _get_aafr_metrics

        result = _get_aafr_metrics()

        self.assertEqual(result["status"], "HEALTHY")
        self.assertEqual(result["1h"]["total"], 0)
        self.assertEqual(result["1h"]["success_rate"], 100.0)


class OpsStreamAAFRKeyTests(TestCase):
    """Verify the OpsStreamView includes 'aafr' key in response."""

    def test_aafr_in_stream_response(self):
        from django.conf import settings
        from apps.users.models import User, TermsAcceptance

        user = User.objects.create_user(
            email="opsadmin@test.com", password="testpass123", is_staff=True
        )
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )

        # OpsStreamView now reads from cache — populate it first
        from apps.core.ai_observability.ops_telemetry import build_ops_stream_payload
        build_ops_stream_payload()

        factory = RequestFactory()
        request = factory.get("/admin-console/ops/stream/")
        request.user = user

        from apps.core.ai_observability.ops_views import OpsStreamView

        response = OpsStreamView.as_view()(request)
        self.assertEqual(response.status_code, 200)

        import json
        data = json.loads(response.content)
        self.assertIn("aafr", data)
