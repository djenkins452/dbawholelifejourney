"""
ICQG — Tests for Intelligence Calibration & Quality Gate.

Covers: repeat suppression, conflict detection, quality gate entry points,
metrics aggregation, ISE integration, and engine integrations.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import TermsAcceptance, User


class ICQGTestBase(TestCase):
    """Base class with common test user setup."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="icqg@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()


# ============================================================
# QualitySuppressionRecord model tests
# ============================================================


class QualitySuppressionRecordModelTest(ICQGTestBase):
    def test_compute_signature_deterministic(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        sig1 = QualitySuppressionRecord.compute_signature("health_check", "Weight trend")
        sig2 = QualitySuppressionRecord.compute_signature("health_check", "Weight trend")
        self.assertEqual(sig1, sig2)

    def test_compute_signature_different_inputs(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        sig1 = QualitySuppressionRecord.compute_signature("health_check", "Weight trend")
        sig2 = QualitySuppressionRecord.compute_signature("health_check", "Sleep quality")
        self.assertNotEqual(sig1, sig2)

    def test_compute_signature_with_evidence_ids(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        sig1 = QualitySuppressionRecord.compute_signature("rule", "title", [1, 2, 3])
        sig2 = QualitySuppressionRecord.compute_signature("rule", "title", [3, 2, 1])
        # Sorted, so should be the same
        self.assertEqual(sig1, sig2)

    def test_create_suppression_record(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        now = timezone.now()
        record = QualitySuppressionRecord.objects.create(
            user=self.user,
            signature_hash="a" * 64,
            suppressed_until=now + timedelta(hours=72),
            last_seen_at=now,
        )
        self.assertEqual(record.count, 1)
        self.assertEqual(record.last_priority, 3)


# ============================================================
# QualityMetricAggregate model tests
# ============================================================


class QualityMetricAggregateModelTest(ICQGTestBase):
    def test_create_metric_aggregate(self):
        from apps.core.ai_quality.quality_models import QualityMetricAggregate

        metric = QualityMetricAggregate.objects.create(
            week_start=timezone.now().date(),
            rule_type="health_trend",
            domain="health",
            delivered_count=10,
            acted_count=4,
            dismissed_count=2,
            usefulness_score=0.65,
        )
        self.assertEqual(metric.delivered_count, 10)
        self.assertEqual(metric.usefulness_score, 0.65)


# ============================================================
# Repeat Suppression tests
# ============================================================


class RepeatSuppressionTest(ICQGTestBase):
    def test_first_occurrence_not_suppressed(self):
        from apps.core.ai_quality.repeat_suppression import check_repeat_suppression

        candidate = {
            "guidance_type": "health_weight_trend",
            "title": "Weight trending up",
            "evidence": {},
            "priority": 3,
        }
        suppressed, reason = check_repeat_suppression(self.user, candidate)
        self.assertFalse(suppressed)
        self.assertIsNone(reason)

    def test_repeat_within_window_suppressed(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        from apps.core.ai_quality.repeat_suppression import (
            _compute_candidate_signature,
            check_repeat_suppression,
        )

        candidate = {
            "guidance_type": "health_weight_trend",
            "title": "Weight trending up",
            "evidence": {},
            "priority": 3,
        }
        sig = _compute_candidate_signature(candidate)
        now = timezone.now()

        # Create existing suppression record
        QualitySuppressionRecord.objects.create(
            user=self.user,
            signature_hash=sig,
            suppressed_until=now + timedelta(hours=72),
            last_seen_at=now - timedelta(hours=1),
            last_priority=3,
        )

        suppressed, reason = check_repeat_suppression(self.user, candidate)
        self.assertTrue(suppressed)
        self.assertIn("Repeat suppression", reason)

    def test_severity_increase_bypasses_suppression(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        from apps.core.ai_quality.repeat_suppression import (
            _compute_candidate_signature,
            check_repeat_suppression,
        )

        candidate = {
            "guidance_type": "health_weight_trend",
            "title": "Weight trending up",
            "evidence": {},
            "priority": 1,  # Higher severity than stored P3
        }
        sig = _compute_candidate_signature(candidate)
        now = timezone.now()

        QualitySuppressionRecord.objects.create(
            user=self.user,
            signature_hash=sig,
            suppressed_until=now + timedelta(hours=72),
            last_seen_at=now - timedelta(hours=1),
            last_priority=3,  # Was P3, now P1
        )

        suppressed, reason = check_repeat_suppression(self.user, candidate)
        self.assertFalse(suppressed)

    def test_expired_window_not_suppressed(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        from apps.core.ai_quality.repeat_suppression import (
            _compute_candidate_signature,
            check_repeat_suppression,
        )

        candidate = {
            "guidance_type": "health_weight_trend",
            "title": "Weight trending up",
            "evidence": {},
            "priority": 3,
        }
        sig = _compute_candidate_signature(candidate)
        now = timezone.now()

        QualitySuppressionRecord.objects.create(
            user=self.user,
            signature_hash=sig,
            suppressed_until=now - timedelta(hours=1),  # Expired
            last_seen_at=now - timedelta(hours=73),
            last_priority=3,
        )

        suppressed, reason = check_repeat_suppression(self.user, candidate)
        self.assertFalse(suppressed)

    def test_record_suppression_creates_record(self):
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord
        from apps.core.ai_quality.repeat_suppression import record_suppression

        candidate = {
            "guidance_type": "new_rule",
            "title": "New guidance",
            "evidence": {},
            "priority": 2,
        }
        record_suppression(self.user, candidate)

        count = QualitySuppressionRecord.objects.filter(user=self.user).count()
        self.assertEqual(count, 1)


# ============================================================
# Conflict Detection tests
# ============================================================


class ConflictDetectionTest(TestCase):
    def test_no_conflict_single_item(self):
        from apps.core.ai_quality.conflict_detector import detect_guidance_conflicts

        candidates = [{"title": "Weight improving", "module": "health", "priority": 2}]
        result = detect_guidance_conflicts(candidates)
        self.assertEqual(len(result), 1)

    def test_no_conflict_same_direction(self):
        from apps.core.ai_quality.conflict_detector import detect_guidance_conflicts

        candidates = [
            {
                "title": "Weight improvement",
                "module": "health",
                "priority": 2,
                "confidence_score": 0.8,
            },
            {
                "title": "Progress on fitness",
                "module": "health",
                "priority": 3,
                "confidence_score": 0.7,
            },
        ]
        result = detect_guidance_conflicts(candidates)
        self.assertEqual(len(result), 2)

    def test_conflict_downgrade_lower_confidence(self):
        from apps.core.ai_quality.conflict_detector import detect_guidance_conflicts

        candidates = [
            {
                "title": "Weight improvement",
                "module": "health",
                "guidance_type": "improvement",
                "priority": 2,
                "confidence_score": 0.9,
            },
            {
                "title": "Weight decline warning",
                "module": "health",
                "guidance_type": "decline",
                "priority": 2,
                "confidence_score": 0.5,
            },
        ]
        result = detect_guidance_conflicts(candidates)
        # Negative was lower confidence, should be downgraded
        negative = [c for c in result if "decline" in c.get("title", "").lower()]
        self.assertTrue(len(negative) > 0)
        self.assertEqual(negative[0]["priority"], 3)  # Downgraded from 2 to 3

    def test_conflict_merge_similar_confidence(self):
        from apps.core.ai_quality.conflict_detector import detect_guidance_conflicts

        candidates = [
            {
                "title": "Weight improvement",
                "module": "health",
                "guidance_type": "improvement",
                "priority": 2,
                "confidence_score": 0.7,
                "message": "Weight is improving",
                "evidence": {},
                "dedupe_key": "test",
            },
            {
                "title": "Weight decline warning",
                "module": "health",
                "guidance_type": "decline",
                "priority": 2,
                "confidence_score": 0.65,
                "message": "Weight is declining",
                "evidence": {},
                "dedupe_key": "test2",
            },
        ]
        result = detect_guidance_conflicts(candidates)
        # Similar confidence -> merged into one "mixed signals" item
        mixed = [c for c in result if c.get("guidance_type") == "mixed_signal"]
        self.assertEqual(len(mixed), 1)
        self.assertIn("Mixed signals", mixed[0]["title"])

    def test_briefing_conflicts(self):
        from apps.core.ai_quality.conflict_detector import detect_briefing_conflicts

        items = [
            {
                "type": "prediction",
                "title": "Weight improvement expected",
                "module": "health",
                "confidence": 0.8,
            },
            {
                "type": "insight",
                "title": "Weight decline detected",
                "module": "health",
                "confidence": 0.5,
                "severity": "warning",
            },
            {"type": "state_change", "title": "General update", "module": "life"},
        ]
        result = detect_briefing_conflicts(items)
        # Should still have 3 items (state_change untouched)
        self.assertEqual(len(result), 3)


# ============================================================
# Quality Gate Entry Point tests
# ============================================================


class QualityGateTest(ICQGTestBase):
    def test_filter_guidance_empty_list(self):
        from apps.core.ai_quality.quality_gate import filter_guidance_candidates

        result = filter_guidance_candidates(self.user, [])
        self.assertEqual(result, [])

    def test_filter_guidance_passes_valid_candidates(self):
        from apps.core.ai_quality.quality_gate import filter_guidance_candidates

        candidates = [
            {
                "guidance_type": "health_trend",
                "title": "Weight stable",
                "priority": 3,
                "source": "sae_state",
                "evidence": {"record_ids": [1]},
            },
        ]
        result = filter_guidance_candidates(self.user, candidates)
        self.assertEqual(len(result), 1)

    def test_filter_guidance_removes_insufficient_evidence(self):
        from apps.core.ai_quality.quality_gate import filter_guidance_candidates

        candidates = [
            {
                "guidance_type": "prediction_rule",
                "title": "Predicted outcome",
                "priority": 3,
                "source": "prie_prediction",
                "evidence": {},
                # No confidence_score — should be filtered
            },
        ]
        result = filter_guidance_candidates(self.user, candidates)
        self.assertEqual(len(result), 0)

    def test_filter_briefing_items_removes_low_confidence(self):
        from apps.core.ai_quality.quality_gate import filter_briefing_items

        items = [
            {
                "type": "prediction",
                "title": "Low confidence pred",
                "confidence": 0.3,
                "module": "health",
            },
            {
                "type": "insight",
                "title": "Good insight",
                "confidence": 0.9,
                "module": "health",
            },
        ]
        result = filter_briefing_items(self.user, items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["type"], "insight")

    def test_filter_delivery_candidates_empty(self):
        from apps.core.ai_quality.quality_gate import filter_delivery_candidates

        result = filter_delivery_candidates(self.user, [])
        self.assertEqual(result, [])

    def test_filter_delivery_passes_normal_items(self):
        from apps.core.ai_quality.quality_gate import filter_delivery_candidates

        items = [
            ("PGE", "GuidanceItem", 1, {"title": "Test", "message": "test"}),
            ("DBE", "DailyBriefing", 2, {"title": "Briefing"}),
        ]
        result = filter_delivery_candidates(self.user, items)
        self.assertEqual(len(result), 2)

    def test_filter_guidance_fail_open(self):
        """ICQG must fail open — never block on error."""
        from apps.core.ai_quality.quality_gate import filter_guidance_candidates

        candidates = [{"title": "Test", "priority": 3}]

        with patch(
            "apps.core.ai_quality.conflict_detector.detect_guidance_conflicts",
            side_effect=Exception("boom"),
        ):
            result = filter_guidance_candidates(self.user, candidates)
        # Should return original candidates on failure
        self.assertEqual(len(result), 1)


# ============================================================
# Metrics Aggregation tests
# ============================================================


class MetricsAggregationTest(ICQGTestBase):
    def test_aggregate_with_no_guidance_items(self):
        from apps.core.ai_quality.quality_metrics import aggregate_weekly_metrics

        result = aggregate_weekly_metrics()
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["errors"], 0)

    def test_response_speed_bonus(self):
        from apps.core.ai_quality.quality_metrics import _response_speed_bonus

        # Fast response: full bonus
        self.assertEqual(_response_speed_bonus(1800), 1.0)
        # Slow response: no bonus
        self.assertEqual(_response_speed_bonus(100000), 0.0)
        # None: no bonus
        self.assertEqual(_response_speed_bonus(None), 0.0)
        # Mid-range: partial bonus
        bonus = _response_speed_bonus(43200)  # 12 hours
        self.assertGreater(bonus, 0.0)
        self.assertLess(bonus, 1.0)


# ============================================================
# ISE Integration tests
# ============================================================


class ISEIntegrationTest(TestCase):
    def test_quality_metrics_task_registered(self):
        from apps.core.ai_scheduler.scheduler_registry import get_registered_tasks

        tasks = get_registered_tasks()
        self.assertIn("aggregate_quality_metrics", tasks)
        self.assertEqual(tasks["aggregate_quality_metrics"]["interval_seconds"], 604800)

    def test_quality_metrics_runner_callable(self):
        from apps.core.ai_scheduler.scheduler_registry import get_task_function

        func = get_task_function("aggregate_quality_metrics")
        self.assertIsNotNone(func)
        self.assertTrue(callable(func))

    def test_quality_metrics_runner_returns_dict(self):
        from apps.core.ai_scheduler.scheduler_runner import (
            run_quality_metrics_aggregation,
        )

        result = run_quality_metrics_aggregation()
        self.assertIn("created", result)
        self.assertIn("updated", result)
        self.assertIn("errors", result)


# ============================================================
# Engine Integration tests (PGE, DBE, WIRE, DNE)
# ============================================================


class PGEIntegrationTest(ICQGTestBase):
    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    @patch("apps.core.ai_guidance.guidance_engine._get_recent_insights")
    @patch("apps.core.ai_guidance.guidance_engine._get_active_predictions")
    @patch("apps.core.ai_guidance.guidance_engine.select_guidance")
    @patch("apps.core.ai_guidance.guidance_engine.rank_guidance")
    @patch("apps.core.ai_guidance.guidance_logger.log_guidance")
    def test_pge_calls_icqg_filter(
        self, mock_log, mock_rank, mock_select, mock_preds, mock_insights, mock_state
    ):
        """PGE generate_guidance calls ICQG filter_guidance_candidates."""
        from apps.core.ai_guidance.guidance_engine import generate_guidance

        mock_state.return_value = {}
        mock_insights.return_value = []
        mock_preds.return_value = []
        mock_select.return_value = [{"title": "Test"}]
        mock_rank.return_value = [
            {
                "title": "Test",
                "guidance_type": "test",
                "priority": 3,
                "source": "sae_state",
                "evidence": {"record_ids": [1]},
            }
        ]
        mock_log.return_value = []

        with patch(
            "apps.core.ai_quality.quality_gate.filter_guidance_candidates",
            wraps=lambda u, c: c,
        ) as mock_icqg:
            generate_guidance(self.user)
            mock_icqg.assert_called_once()

    @patch("apps.core.ai_guidance.guidance_engine._get_user_state")
    @patch("apps.core.ai_guidance.guidance_engine._get_recent_insights")
    @patch("apps.core.ai_guidance.guidance_engine._get_active_predictions")
    @patch("apps.core.ai_guidance.guidance_engine.select_guidance")
    @patch("apps.core.ai_guidance.guidance_engine.rank_guidance")
    @patch("apps.core.ai_guidance.guidance_logger.log_guidance")
    def test_pge_continues_if_icqg_fails(
        self, mock_log, mock_rank, mock_select, mock_preds, mock_insights, mock_state
    ):
        """PGE must not break if ICQG raises an exception."""
        from apps.core.ai_guidance.guidance_engine import generate_guidance

        mock_state.return_value = {}
        mock_insights.return_value = []
        mock_preds.return_value = []
        mock_select.return_value = [{"title": "Test"}]
        mock_rank.return_value = [{"title": "Test", "priority": 3}]
        mock_log.return_value = [MagicMock()]

        with patch(
            "apps.core.ai_quality.quality_gate.filter_guidance_candidates",
            side_effect=Exception("ICQG crash"),
        ):
            result = generate_guidance(self.user)
            # Should still return items (ICQG failed, so unfiltered list used)
            self.assertEqual(len(result), 1)


class DBEIntegrationTest(ICQGTestBase):
    @patch("apps.core.ai_briefing.briefing_engine._get_state")
    @patch("apps.core.ai_briefing.briefing_engine._get_guidance")
    @patch("apps.core.ai_briefing.briefing_engine._get_insights")
    @patch("apps.core.ai_briefing.briefing_engine._get_predictions")
    @patch("apps.core.ai_briefing.briefing_engine.select_briefing_items")
    @patch("apps.core.ai_briefing.briefing_engine.rank_briefing_items")
    @patch("apps.core.ai_briefing.briefing_engine.store_briefing")
    def test_dbe_calls_icqg_filter(
        self, mock_store, mock_rank, mock_select, mock_preds, mock_insights,
        mock_guidance, mock_state
    ):
        """DBE generate_daily_briefing calls ICQG filter_briefing_items."""
        from apps.core.ai_briefing.briefing_engine import generate_daily_briefing

        mock_state.return_value = {}
        mock_guidance.return_value = []
        mock_insights.return_value = []
        mock_preds.return_value = []
        mock_select.return_value = [{"type": "insight", "title": "Test"}]
        mock_rank.return_value = [{"type": "insight", "title": "Test"}]
        mock_store.return_value = MagicMock()

        with patch(
            "apps.core.ai_quality.quality_gate.filter_briefing_items",
            wraps=lambda u, i: i,
        ) as mock_icqg:
            generate_daily_briefing(self.user)
            mock_icqg.assert_called_once()


class DNEIntegrationTest(ICQGTestBase):
    @patch("apps.core.ai_delivery.delivery_engine._get_enabled_channels")
    @patch("apps.core.ai_delivery.delivery_engine._get_undelivered_guidance")
    @patch("apps.core.ai_delivery.delivery_engine._get_undelivered_briefings")
    @patch("apps.core.ai_delivery.delivery_engine._get_undelivered_reports")
    @patch("apps.core.ai_delivery.delivery_engine._deliver_to_channel")
    def test_dne_calls_icqg_filter(
        self, mock_deliver, mock_reports, mock_briefings, mock_guidance, mock_channels
    ):
        """DNE _deliver_for_user calls ICQG filter_delivery_candidates."""
        from apps.core.ai_delivery.delivery_engine import _deliver_for_user

        mock_channels.return_value = ["in_app"]
        mock_guidance.return_value = [
            ("PGE", "GuidanceItem", 1, {"title": "Test"})
        ]
        mock_briefings.return_value = []
        mock_reports.return_value = []
        mock_deliver.return_value = True

        with patch(
            "apps.core.ai_quality.quality_gate.filter_delivery_candidates",
            wraps=lambda u, i: i,
        ) as mock_icqg:
            _deliver_for_user(self.user)
            mock_icqg.assert_called_once()


# ============================================================
# Admin tests
# ============================================================


class ICQGAdminTest(ICQGTestBase):
    def test_suppression_admin_registered(self):
        from django.contrib.admin import site
        from apps.core.ai_quality.quality_models import QualitySuppressionRecord

        self.assertIn(QualitySuppressionRecord, site._registry)

    def test_metric_aggregate_admin_registered(self):
        from django.contrib.admin import site
        from apps.core.ai_quality.quality_models import QualityMetricAggregate

        self.assertIn(QualityMetricAggregate, site._registry)
