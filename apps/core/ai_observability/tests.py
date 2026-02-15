"""
IOCD — Tests for Intelligence Observability & Calibration Dashboard.

Tests cover:
- IntelligenceMetricsSnapshot model
- Metrics calculator
- Observability engine
- Dashboard view (staff-only)
- ICC integration
- ISE scheduler registration
- Admin registration

Project: Whole Life Journey
Path: apps/core/ai_observability/tests.py

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError
from django.test import TestCase, RequestFactory, override_settings
from django.utils import timezone

from apps.core.ai_observability.models import IntelligenceMetricsSnapshot
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="test@example.com", is_staff=False):
    """Create a test user with required onboarding."""
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.save()
    if is_staff:
        user.is_staff = True
        user.save()
    return user


# ============================================================
# Model Tests
# ============================================================
class TestIntelligenceMetricsSnapshotModel(TestCase):
    """Test IntelligenceMetricsSnapshot model."""

    def test_create_snapshot(self):
        """Can create a snapshot with defaults."""
        snapshot = IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today(),
        )
        self.assertEqual(snapshot.snapshot_date, date.today())
        self.assertEqual(snapshot.guidance_total, 0)
        self.assertEqual(snapshot.deliveries_by_channel, {})
        self.assertEqual(snapshot.persona_effectiveness_scores, {})
        self.assertIsNotNone(snapshot.created_at)

    def test_unique_constraint(self):
        """Cannot create two snapshots for the same date."""
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today(),
        )
        with self.assertRaises(IntegrityError):
            IntelligenceMetricsSnapshot.objects.create(
                snapshot_date=date.today(),
            )

    def test_defaults_are_zero(self):
        """All numeric defaults are 0."""
        snapshot = IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today(),
        )
        self.assertEqual(snapshot.guidance_acceptance_rate, 0.0)
        self.assertEqual(snapshot.guidance_action_rate, 0.0)
        self.assertEqual(snapshot.predictions_avg_confidence, 0.0)
        self.assertEqual(snapshot.deliveries_success_rate, 0.0)
        self.assertEqual(snapshot.avg_responsiveness_score, 0.0)
        self.assertEqual(snapshot.avg_usefulness_score, 0.0)
        self.assertEqual(snapshot.total_suppressed, 0)

    def test_str_representation(self):
        """String representation includes date."""
        snapshot = IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date(2026, 2, 15),
        )
        self.assertIn("2026-02-15", str(snapshot))

    def test_ordering(self):
        """Snapshots are ordered by date descending."""
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date(2026, 2, 10),
        )
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date(2026, 2, 15),
        )
        snapshots = list(IntelligenceMetricsSnapshot.objects.all())
        self.assertEqual(snapshots[0].snapshot_date, date(2026, 2, 15))
        self.assertEqual(snapshots[1].snapshot_date, date(2026, 2, 10))


# ============================================================
# Metrics Calculator Tests
# ============================================================
class TestMetricsCalculatorEmptyDB(TestCase):
    """Test calculator when no data exists."""

    def test_empty_db_returns_zeros(self):
        """All metrics default to zero when DB is empty."""
        from apps.core.ai_observability.metrics_calculator import (
            calculate_daily_metrics,
        )

        metrics = calculate_daily_metrics()
        self.assertEqual(metrics["guidance_total"], 0)
        self.assertEqual(metrics["predictions_total"], 0)
        self.assertEqual(metrics["deliveries_total"], 0)
        self.assertEqual(metrics["active_users_count"], 0)
        self.assertEqual(metrics["avg_usefulness_score"], 0.0)
        self.assertEqual(metrics["persona_effectiveness_scores"], {})


class TestMetricsCalculatorGuidance(TestCase):
    """Test guidance metrics calculation."""

    def setUp(self):
        self.user = _create_test_user()

    def test_guidance_counts(self):
        """Correctly counts guidance items by status."""
        from apps.core.ai_guidance.models import GuidanceItem

        # Create items with different statuses
        GuidanceItem.objects.create(
            user=self.user,
            title="Acknowledged",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="ack1",
            acknowledged_at=timezone.now(),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Dismissed",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="dis1",
            dismissed_at=timezone.now(),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Acted",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="act1",
            acted_upon_at=timezone.now(),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Active",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="active1",
        )

        from apps.core.ai_observability.metrics_calculator import (
            _calculate_guidance_metrics,
        )

        metrics = _calculate_guidance_metrics()
        self.assertEqual(metrics["guidance_total"], 4)
        self.assertEqual(metrics["guidance_acknowledged"], 1)
        self.assertEqual(metrics["guidance_dismissed"], 1)
        self.assertEqual(metrics["guidance_acted"], 1)
        self.assertAlmostEqual(
            metrics["guidance_acceptance_rate"], 0.25, places=2
        )
        self.assertAlmostEqual(
            metrics["guidance_action_rate"], 0.25, places=2
        )


class TestMetricsCalculatorPredictions(TestCase):
    """Test prediction metrics calculation."""

    def setUp(self):
        self.user = _create_test_user()

    def test_prediction_counts(self):
        """Correctly counts predictions by status."""
        from apps.core.ai_predictions.models import Prediction

        Prediction.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            module="health",
            confidence_score=0.85,
            predicted_date=timezone.now() + timedelta(days=30),
            explanation="Test",
            evidence={},
            status="active",
            dedupe_key="pred1",
        )
        Prediction.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            module="health",
            confidence_score=0.60,
            predicted_date=timezone.now() - timedelta(days=30),
            explanation="Test",
            evidence={},
            status="expired",
            dedupe_key="pred2",
        )

        from apps.core.ai_observability.metrics_calculator import (
            _calculate_prediction_metrics,
        )

        metrics = _calculate_prediction_metrics()
        self.assertEqual(metrics["predictions_total"], 2)
        self.assertEqual(metrics["predictions_active"], 1)
        self.assertEqual(metrics["predictions_expired"], 1)
        self.assertAlmostEqual(
            metrics["predictions_avg_confidence"], 0.85, places=2
        )


class TestMetricsCalculatorDelivery(TestCase):
    """Test delivery metrics calculation."""

    def setUp(self):
        self.user = _create_test_user()

    def test_delivery_counts(self):
        """Correctly counts deliveries by status and channel."""
        from apps.core.ai_delivery.models import DeliveredNotification

        DeliveredNotification.objects.create(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            channel="in_app",
            title="Test",
            message="Test",
            status="sent",
            dedupe_hash="hash1",
        )
        DeliveredNotification.objects.create(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=2,
            channel="email",
            title="Test",
            message="Test",
            status="skipped",
            skip_reason="throttle",
            dedupe_hash="hash2",
        )

        from apps.core.ai_observability.metrics_calculator import (
            _calculate_delivery_metrics,
        )

        metrics = _calculate_delivery_metrics()
        self.assertEqual(metrics["deliveries_total"], 2)
        self.assertEqual(metrics["deliveries_sent"], 1)
        self.assertEqual(metrics["deliveries_skipped"], 1)
        self.assertAlmostEqual(
            metrics["deliveries_success_rate"], 0.5, places=2
        )
        self.assertEqual(metrics["deliveries_by_channel"]["in_app"], 1)
        self.assertEqual(metrics["deliveries_by_channel"]["email"], 1)


class TestMetricsCalculatorSourceFailure(TestCase):
    """Test that individual source failures don't crash calculator."""

    def test_all_sources_return_dict_on_empty_db(self):
        """Each source calculator returns a dict even with no data."""
        from apps.core.ai_observability.metrics_calculator import (
            _calculate_guidance_metrics,
            _calculate_prediction_metrics,
            _calculate_delivery_metrics,
            _calculate_engagement_metrics,
            _calculate_quality_metrics,
            _calculate_persona_metrics,
        )

        for fn in [
            _calculate_guidance_metrics,
            _calculate_prediction_metrics,
            _calculate_delivery_metrics,
            _calculate_engagement_metrics,
            _calculate_quality_metrics,
            _calculate_persona_metrics,
        ]:
            result = fn()
            self.assertIsInstance(
                result, dict, f"{fn.__name__} should return dict"
            )

    def test_full_calculator_returns_all_keys(self):
        """calculate_daily_metrics returns dict with all required keys."""
        from apps.core.ai_observability.metrics_calculator import (
            calculate_daily_metrics,
        )

        metrics = calculate_daily_metrics()
        required_keys = [
            "guidance_total",
            "predictions_total",
            "deliveries_total",
            "active_users_count",
            "avg_usefulness_score",
            "persona_effectiveness_scores",
        ]
        for key in required_keys:
            self.assertIn(key, metrics, f"Missing key: {key}")


class TestMetricsCalculatorPersona(TestCase):
    """Test persona effectiveness calculation."""

    def setUp(self):
        self.user = _create_test_user()

    def test_persona_grouping(self):
        """Groups guidance action/dismiss rates by coaching style."""
        from apps.core.ai_guidance.models import GuidanceItem

        # User's default style is 'supportive'
        GuidanceItem.objects.create(
            user=self.user,
            title="Item 1",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="p1",
            acted_upon_at=timezone.now(),
        )
        GuidanceItem.objects.create(
            user=self.user,
            title="Item 2",
            message="Test",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="p2",
            dismissed_at=timezone.now(),
        )

        from apps.core.ai_observability.metrics_calculator import (
            _calculate_persona_metrics,
        )

        metrics = _calculate_persona_metrics()
        scores = metrics["persona_effectiveness_scores"]
        self.assertIn("supportive", scores)
        self.assertEqual(scores["supportive"]["total"], 2)
        self.assertEqual(scores["supportive"]["acted"], 1)
        self.assertEqual(scores["supportive"]["dismissed"], 1)


# ============================================================
# Observability Engine Tests
# ============================================================
class TestObservabilityEngine(TestCase):
    """Test observability engine."""

    def test_generates_snapshot(self):
        """Creates a new snapshot for yesterday."""
        from apps.core.ai_observability.observability_engine import (
            generate_daily_snapshot,
        )

        yesterday = date.today() - timedelta(days=1)
        snapshot = generate_daily_snapshot(yesterday)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.snapshot_date, yesterday)

    def test_skips_duplicate(self):
        """Returns existing snapshot if one already exists."""
        from apps.core.ai_observability.observability_engine import (
            generate_daily_snapshot,
        )

        yesterday = date.today() - timedelta(days=1)
        first = generate_daily_snapshot(yesterday)
        second = generate_daily_snapshot(yesterday)
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            IntelligenceMetricsSnapshot.objects.filter(
                snapshot_date=yesterday
            ).count(),
            1,
        )

    def test_defaults_to_yesterday(self):
        """Without target_date, generates for yesterday."""
        from apps.core.ai_observability.observability_engine import (
            generate_daily_snapshot,
        )

        snapshot = generate_daily_snapshot()
        expected = date.today() - timedelta(days=1)
        self.assertEqual(snapshot.snapshot_date, expected)

    def test_get_latest_snapshot(self):
        """get_latest_snapshot returns most recent."""
        from apps.core.ai_observability.observability_engine import (
            get_latest_snapshot,
        )

        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date(2026, 2, 10),
        )
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date(2026, 2, 14),
        )
        latest = get_latest_snapshot()
        self.assertEqual(latest.snapshot_date, date(2026, 2, 14))

    def test_get_snapshot_history(self):
        """get_snapshot_history returns snapshots within range."""
        from apps.core.ai_observability.observability_engine import (
            get_snapshot_history,
        )

        today = date.today()
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=today - timedelta(days=5),
        )
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=today - timedelta(days=50),
        )
        history = get_snapshot_history(days=30)
        self.assertEqual(history.count(), 1)

    @patch(
        "apps.core.ai_observability.observability_engine.calculate_daily_metrics",
        side_effect=Exception("boom"),
    )
    def test_returns_none_on_error(self, mock_calc):
        """Returns None on calculation error."""
        from apps.core.ai_observability.observability_engine import (
            generate_daily_snapshot,
        )

        result = generate_daily_snapshot(date.today() - timedelta(days=2))
        self.assertIsNone(result)


# ============================================================
# View Tests
# ============================================================
class TestObservabilityDashboardView(TestCase):
    """Test observability dashboard view (staff-only) via RequestFactory."""

    def setUp(self):
        self.factory = RequestFactory()
        self.staff_user = _create_test_user(
            email="staff@example.com", is_staff=True,
        )
        self.regular_user = _create_test_user(
            email="regular@example.com", is_staff=False,
        )

    def _get_view_response(self, user):
        """Helper to call the view with RequestFactory."""
        from apps.core.ai_observability.views import (
            ObservabilityDashboardView,
        )

        request = self.factory.get("/intelligence/observability/")
        request.user = user
        view = ObservabilityDashboardView.as_view()
        return view(request)

    def test_staff_can_access(self):
        """Staff users can access the observability dashboard."""
        response = self._get_view_response(self.staff_user)
        self.assertEqual(response.status_code, 200)

    def test_non_staff_denied(self):
        """Non-staff users are denied access."""
        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            self._get_view_response(self.regular_user)

    def test_context_has_snapshot(self):
        """Context includes snapshot when data exists."""
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today() - timedelta(days=1),
            guidance_total=10,
            guidance_action_rate=0.5,
        )
        from apps.core.ai_observability.views import (
            ObservabilityDashboardView,
        )

        request = self.factory.get("/intelligence/observability/")
        request.user = self.staff_user
        view = ObservabilityDashboardView()
        view.request = request
        context = view.get_context_data()
        self.assertIsNotNone(context["snapshot"])
        self.assertEqual(context["snapshot"].guidance_total, 10)

    def test_empty_state(self):
        """Page works with no snapshot data."""
        from apps.core.ai_observability.views import (
            ObservabilityDashboardView,
        )

        request = self.factory.get("/intelligence/observability/")
        request.user = self.staff_user
        view = ObservabilityDashboardView()
        view.request = request
        context = view.get_context_data()
        self.assertIsNone(context["snapshot"])

    def test_context_has_history(self):
        """Context includes history list."""
        for i in range(3):
            IntelligenceMetricsSnapshot.objects.create(
                snapshot_date=date.today() - timedelta(days=i + 1),
            )
        from apps.core.ai_observability.views import (
            ObservabilityDashboardView,
        )

        request = self.factory.get("/intelligence/observability/")
        request.user = self.staff_user
        view = ObservabilityDashboardView()
        view.request = request
        context = view.get_context_data()
        self.assertEqual(len(context["history"]), 3)

    def test_trends_computed(self):
        """Trends computed when multiple snapshots exist."""
        for i in range(3):
            IntelligenceMetricsSnapshot.objects.create(
                snapshot_date=date.today() - timedelta(days=i + 1),
                guidance_action_rate=0.5 + (i * 0.1),
            )
        from apps.core.ai_observability.views import (
            ObservabilityDashboardView,
        )

        request = self.factory.get("/intelligence/observability/")
        request.user = self.staff_user
        view = ObservabilityDashboardView()
        view.request = request
        context = view.get_context_data()
        self.assertIsInstance(context["trends"], dict)


# ============================================================
# ICC Integration Tests
# ============================================================
@override_settings(ROOT_URLCONF="config.urls")
class TestICCObservabilityIntegration(TestCase):
    """Test observability section in ICC via unit tests on the view."""

    def test_staff_gets_observability_in_context(self):
        """ICC view adds observability_snapshot for staff users."""
        user = _create_test_user(email="icc_staff@example.com", is_staff=True)
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today() - timedelta(days=1),
            guidance_action_rate=0.5,
        )

        from apps.core.views_intelligence_center import (
            IntelligenceCommandCenterView,
        )
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/intelligence/")
        request.user = user
        view = IntelligenceCommandCenterView()
        view.request = request
        context = view.get_context_data()
        self.assertIn("observability_snapshot", context)
        self.assertIsNotNone(context["observability_snapshot"])

    def test_non_staff_no_observability_in_context(self):
        """ICC view does not add observability for non-staff users."""
        user = _create_test_user(email="icc_regular@example.com", is_staff=False)
        IntelligenceMetricsSnapshot.objects.create(
            snapshot_date=date.today() - timedelta(days=1),
        )

        from apps.core.views_intelligence_center import (
            IntelligenceCommandCenterView,
        )
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/intelligence/")
        request.user = user
        view = IntelligenceCommandCenterView()
        view.request = request
        context = view.get_context_data()
        self.assertNotIn("observability_snapshot", context)

    def test_staff_no_snapshot_returns_none(self):
        """ICC returns None for observability when no snapshot exists."""
        user = _create_test_user(email="icc_staff2@example.com", is_staff=True)

        from apps.core.views_intelligence_center import (
            IntelligenceCommandCenterView,
        )
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/intelligence/")
        request.user = user
        view = IntelligenceCommandCenterView()
        view.request = request
        context = view.get_context_data()
        self.assertIsNone(context.get("observability_snapshot"))


# ============================================================
# Scheduler Tests
# ============================================================
class TestSchedulerRegistration(TestCase):
    """Test IOCD registration with ISE scheduler."""

    def test_task_registered(self):
        """Observability snapshot task is in the registry."""
        from apps.core.ai_scheduler.scheduler_registry import (
            get_registered_tasks,
        )

        tasks = get_registered_tasks()
        self.assertIn("generate_observability_snapshot", tasks)
        self.assertEqual(
            tasks["generate_observability_snapshot"]["interval_seconds"],
            86400,
        )

    def test_runner_calls_engine(self):
        """Runner function calls generate_daily_snapshot."""
        from apps.core.ai_scheduler.scheduler_runner import (
            run_observability_snapshot,
        )

        result = run_observability_snapshot()
        self.assertIn("generated", result)
        # Should succeed (generates for yesterday)
        self.assertEqual(result["generated"], 1)
        self.assertEqual(result["errors"], 0)

    @patch(
        "apps.core.ai_observability.observability_engine.generate_daily_snapshot",
        return_value=None,
    )
    def test_runner_handles_failure(self, mock_fn):
        """Runner reports error when engine returns None."""
        from apps.core.ai_scheduler.scheduler_runner import (
            run_observability_snapshot,
        )

        result = run_observability_snapshot()
        self.assertEqual(result["generated"], 0)
        self.assertEqual(result["errors"], 1)


# ============================================================
# Management Command Tests
# ============================================================
class TestManagementCommand(TestCase):
    """Test generate_observability_snapshots management command."""

    def test_backfill_creates_snapshots(self):
        """--days N creates snapshots for last N days."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command(
            "generate_observability_snapshots", "--days", "3", stdout=out,
        )
        self.assertEqual(
            IntelligenceMetricsSnapshot.objects.count(), 3,
        )

    def test_default_creates_one(self):
        """Default creates 1 snapshot (yesterday)."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("generate_observability_snapshots", stdout=out)
        self.assertEqual(
            IntelligenceMetricsSnapshot.objects.count(), 1,
        )


# ============================================================
# Admin Tests
# ============================================================
class TestAdmin(TestCase):
    """Test admin registration."""

    def test_admin_read_only(self):
        """Admin has no add/change permissions."""
        from apps.core.ai_observability.admin import (
            IntelligenceMetricsSnapshotAdmin,
        )
        from django.contrib.admin.sites import AdminSite

        admin_instance = IntelligenceMetricsSnapshotAdmin(
            IntelligenceMetricsSnapshot, AdminSite()
        )
        factory = RequestFactory()
        request = factory.get("/")
        self.assertFalse(admin_instance.has_add_permission(request))
        self.assertFalse(admin_instance.has_change_permission(request))

    def test_list_display_fields(self):
        """Admin list_display includes key fields."""
        from apps.core.ai_observability.admin import (
            IntelligenceMetricsSnapshotAdmin,
        )

        self.assertIn(
            "snapshot_date",
            IntelligenceMetricsSnapshotAdmin.list_display,
        )
        self.assertIn(
            "guidance_action_rate",
            IntelligenceMetricsSnapshotAdmin.list_display,
        )
