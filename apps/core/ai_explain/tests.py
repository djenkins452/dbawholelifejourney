"""
E3 — Evidence & Explainability Engine Tests.

Covers:
- ExplainRecord model creation
- Evidence builder for guidance, briefing, weekly report
- Explain templates for all three types
- Explain engine (ensure_explain_record, get_explain_record)
- Explain logger deduplication
- Explain detail view (permissions, on-demand creation)
- "Why?" link rendering on guidance inbox, briefing tile, weekly report detail
"""

from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.core.ai_briefing.models import DailyBriefing
from apps.core.ai_explain.evidence_builder import (
    build_evidence_for_briefing,
    build_evidence_for_guidance,
    build_evidence_for_weekly_report,
)
from apps.core.ai_explain.explain_engine import (
    ensure_explain_record,
    get_explain_record,
)
from apps.core.ai_explain.explain_logger import store_explain_record
from apps.core.ai_explain.explain_templates import (
    explain_briefing,
    explain_guidance,
    explain_weekly_report,
)
from apps.core.ai_explain.models import ExplainRecord
from apps.core.ai_guidance.models import GuidanceItem
from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport
from apps.users.models import TermsAcceptance

User = get_user_model()


def _setup_test_user(email="e3test@example.com", password="testpass123"):
    """Create a test user with onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.ai_enabled = True
    user.preferences.save()
    return user


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


class ExplainRecordModelTest(TestCase):
    """Tests for the ExplainRecord model."""

    def setUp(self):
        self.user = _setup_test_user()

    def test_create_explain_record(self):
        """An explain record can be created with required fields."""
        record = ExplainRecord.objects.create(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            title="Test guidance",
            explanation="This was generated because...",
            evidence=[{"type": "insight", "summary": "Weight loss"}],
        )
        self.assertEqual(record.source_engine, "PGE")
        self.assertEqual(record.source_object_type, "GuidanceItem")
        self.assertIsInstance(record.evidence, list)

    def test_default_evidence_is_list(self):
        """Evidence defaults to empty list."""
        record = ExplainRecord.objects.create(
            user=self.user,
            source_engine="DBE",
            source_object_type="DailyBriefing",
            source_object_id=1,
            title="Test",
            explanation="Explanation",
        )
        self.assertEqual(record.evidence, [])

    def test_str_representation(self):
        """__str__ includes engine and object info."""
        record = ExplainRecord.objects.create(
            user=self.user,
            source_engine="WIRE",
            source_object_type="WeeklyIntelligenceReport",
            source_object_id=42,
            title="Test",
            explanation="Explanation",
        )
        self.assertIn("WIRE", str(record))
        self.assertIn("42", str(record))


# ---------------------------------------------------------------------------
# Evidence Builder Tests
# ---------------------------------------------------------------------------


class EvidenceBuilderGuidanceTest(TestCase):
    """Tests for build_evidence_for_guidance."""

    def setUp(self):
        self.user = _setup_test_user()
        self.item = GuidanceItem.objects.create(
            user=self.user,
            title="Check your weight",
            message="Your weight is trending up",
            priority=2,
            guidance_type="health_trend",
            source="sae_state",
            module="health",
            confidence_score=0.85,
            evidence={
                "data_points": [
                    {"name": "weight_trend", "value": "increasing"},
                    {"name": "bmi_above_target", "value": True},
                ]
            },
            dedupe_key="test_weight_trend",
        )

    def test_evidence_extracted_from_data_points(self):
        """Evidence includes items from the guidance evidence field."""
        evidence = build_evidence_for_guidance(self.item)
        self.assertTrue(len(evidence) >= 2)
        summaries = [e["summary"] for e in evidence]
        self.assertTrue(any("Weight Trend" in s for s in summaries))

    def test_module_link_included(self):
        """Evidence includes a module link for health."""
        evidence = build_evidence_for_guidance(self.item)
        module_links = [e for e in evidence if e["type"] == "module_link"]
        self.assertEqual(len(module_links), 1)
        self.assertEqual(module_links[0]["url"], "/health/")

    def test_fallback_when_no_data_points(self):
        """Provides fallback evidence when no data points exist."""
        self.item.evidence = {}
        self.item.save()
        evidence = build_evidence_for_guidance(self.item)
        self.assertTrue(len(evidence) >= 1)


class EvidenceBuilderBriefingTest(TestCase):
    """Tests for build_evidence_for_briefing."""

    def setUp(self):
        self.user = _setup_test_user()
        self.briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=date(2026, 2, 15),
            summary="Good morning! Here's your briefing.",
            guidance_snapshot={
                "items": [{"id": 1, "title": "Check weight", "source": "sae_state", "priority": 2, "module": "health"}],
                "count": 1,
            },
            insight_snapshot={
                "items": [{"id": 1, "title": "Sleep improved", "severity": "info", "module": "health"}],
                "count": 1,
            },
            prediction_snapshot={
                "items": [{"id": 1, "prediction_type": "weight", "confidence_score": 0.85, "module": "health"}],
                "count": 1,
            },
        )

    def test_evidence_includes_guidance_items(self):
        """Evidence includes guidance snapshot items."""
        evidence = build_evidence_for_briefing(self.briefing)
        guidance_items = [e for e in evidence if e["type"] == "guidance_item"]
        self.assertEqual(len(guidance_items), 1)

    def test_evidence_includes_insights(self):
        """Evidence includes insight snapshot items."""
        evidence = build_evidence_for_briefing(self.briefing)
        insight_items = [e for e in evidence if e["type"] == "insight"]
        self.assertEqual(len(insight_items), 1)

    def test_evidence_includes_predictions(self):
        """Evidence includes prediction snapshot items."""
        evidence = build_evidence_for_briefing(self.briefing)
        prediction_items = [e for e in evidence if e["type"] == "prediction"]
        self.assertEqual(len(prediction_items), 1)

    def test_empty_briefing_fallback(self):
        """Empty briefing has fallback evidence."""
        self.briefing.guidance_snapshot = {}
        self.briefing.insight_snapshot = {}
        self.briefing.prediction_snapshot = {}
        self.briefing.save()
        evidence = build_evidence_for_briefing(self.briefing)
        self.assertTrue(len(evidence) >= 1)


class EvidenceBuilderWeeklyReportTest(TestCase):
    """Tests for build_evidence_for_weekly_report."""

    def setUp(self):
        self.user = _setup_test_user()
        self.report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Your weekly summary",
            state_delta_snapshot={"deltas": [{"label": "Weight trend: down", "significant": True}]},
            insight_snapshot={"insights": [{"title": "Sleep improved", "severity": "info", "created_at": "2026-02-10T00:00:00"}]},
            prediction_snapshot={"predictions": [{"title": "Weight: 175", "confidence_score": 0.85, "created_at": "2026-02-10T00:00:00"}]},
            guidance_snapshot={"guidance": [{"title": "Check weight", "acted": True}]},
            learning_snapshot={"responsiveness_score": 0.7, "total_guidance_seen": 10},
        )

    def test_evidence_includes_state_changes(self):
        """Evidence includes state delta items."""
        evidence = build_evidence_for_weekly_report(self.report)
        state_items = [e for e in evidence if e["type"] == "state_change"]
        self.assertEqual(len(state_items), 1)

    def test_evidence_includes_learning_profile(self):
        """Evidence includes learning engagement score."""
        evidence = build_evidence_for_weekly_report(self.report)
        learning = [e for e in evidence if e["type"] == "learning_profile"]
        self.assertEqual(len(learning), 1)
        self.assertIn("70%", learning[0]["summary"])

    def test_evidence_includes_acted_guidance_count(self):
        """Evidence includes guidance interaction count."""
        evidence = build_evidence_for_weekly_report(self.report)
        interactions = [e for e in evidence if e["type"] == "guidance_interaction"]
        self.assertEqual(len(interactions), 1)


# ---------------------------------------------------------------------------
# Explain Templates Tests
# ---------------------------------------------------------------------------


class ExplainTemplatesTest(TestCase):
    """Tests for explain_templates module."""

    def setUp(self):
        self.user = _setup_test_user()

    def test_guidance_explanation_includes_rule(self):
        """Guidance explanation mentions the rule type."""
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Test",
            message="Message",
            priority=2,
            guidance_type="health_trend",
            source="sae_state",
            module="health",
            dedupe_key="test_explain",
        )
        explanation, _ = explain_guidance(item)
        self.assertIn("health trend", explanation)
        self.assertIn("health", explanation)

    def test_guidance_confidence_high(self):
        """High confidence gets appropriate explanation."""
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Test",
            message="Message",
            priority=3,
            guidance_type="test",
            source="prie_prediction",
            confidence_score=0.9,
            dedupe_key="test_conf",
        )
        _, conf_exp = explain_guidance(item)
        self.assertIsNotNone(conf_exp)
        self.assertIn("90%", conf_exp)
        self.assertIn("strong", conf_exp)

    def test_guidance_confidence_low(self):
        """Low confidence gets early-signal explanation."""
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Test",
            message="Message",
            priority=3,
            guidance_type="test",
            source="prie_prediction",
            confidence_score=0.3,
            dedupe_key="test_low_conf",
        )
        _, conf_exp = explain_guidance(item)
        self.assertIn("early signal", conf_exp)

    def test_briefing_explanation(self):
        """Briefing explanation includes item counts."""
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=date(2026, 2, 15),
            summary="Test",
            guidance_snapshot={"count": 2, "items": []},
            insight_snapshot={"count": 1, "items": []},
            prediction_snapshot={"count": 0, "items": []},
        )
        explanation, _ = explain_briefing(briefing)
        self.assertIn("2 guidance items", explanation)
        self.assertIn("1 insight", explanation)

    def test_weekly_report_explanation(self):
        """Weekly report explanation includes date range."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Test",
        )
        explanation, _ = explain_weekly_report(report)
        self.assertIn("2026-02-09", explanation)
        self.assertIn("2026-02-15", explanation)


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------


class ExplainEngineTest(TestCase):
    """Tests for the explain engine entry point."""

    def setUp(self):
        self.user = _setup_test_user()
        self.item = GuidanceItem.objects.create(
            user=self.user,
            title="Check weight",
            message="Your weight is trending up",
            priority=2,
            guidance_type="health_trend",
            source="sae_state",
            module="health",
            dedupe_key="test_engine",
        )

    def test_ensure_creates_record(self):
        """ensure_explain_record creates a new record."""
        record = ensure_explain_record(self.user, "PGE", self.item)
        self.assertIsNotNone(record)
        self.assertIsInstance(record, ExplainRecord)
        self.assertEqual(record.source_engine, "PGE")
        self.assertEqual(record.source_object_type, "GuidanceItem")
        self.assertEqual(record.source_object_id, self.item.pk)

    def test_ensure_returns_existing(self):
        """Calling ensure twice returns the same record."""
        record1 = ensure_explain_record(self.user, "PGE", self.item)
        record2 = ensure_explain_record(self.user, "PGE", self.item)
        self.assertEqual(record1.id, record2.id)
        self.assertEqual(ExplainRecord.objects.count(), 1)

    def test_get_explain_record(self):
        """get_explain_record finds existing records."""
        ensure_explain_record(self.user, "PGE", self.item)
        record = get_explain_record(self.user, "PGE", "GuidanceItem", self.item.pk)
        self.assertIsNotNone(record)

    def test_get_explain_record_none(self):
        """get_explain_record returns None when not found."""
        record = get_explain_record(self.user, "PGE", "GuidanceItem", 999)
        self.assertIsNone(record)

    def test_ensure_for_briefing(self):
        """ensure_explain_record works for DailyBriefing."""
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=date(2026, 2, 15),
            summary="Test",
        )
        record = ensure_explain_record(self.user, "DBE", briefing)
        self.assertIsNotNone(record)
        self.assertEqual(record.source_engine, "DBE")

    def test_ensure_for_weekly_report(self):
        """ensure_explain_record works for WeeklyIntelligenceReport."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Test",
        )
        record = ensure_explain_record(self.user, "WIRE", report)
        self.assertIsNotNone(record)
        self.assertEqual(record.source_engine, "WIRE")

    def test_ensure_handles_unknown_type(self):
        """Unknown object type returns None gracefully."""
        class FakeObj:
            pk = 1
        record = ensure_explain_record(self.user, "X", FakeObj())
        self.assertIsNone(record)


# ---------------------------------------------------------------------------
# Logger Tests
# ---------------------------------------------------------------------------


class ExplainLoggerTest(TestCase):
    """Tests for the explain_logger module."""

    def setUp(self):
        self.user = _setup_test_user()

    def test_store_new_record(self):
        """store_explain_record creates a new record."""
        record = store_explain_record(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            title="Test",
            explanation="Because...",
            evidence=[{"type": "insight", "summary": "test"}],
        )
        self.assertIsNotNone(record)
        self.assertEqual(ExplainRecord.objects.count(), 1)

    def test_dedup_returns_existing(self):
        """Storing duplicate returns existing record."""
        record1 = store_explain_record(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            title="First",
            explanation="First",
            evidence=[],
        )
        record2 = store_explain_record(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            title="Second",
            explanation="Second",
            evidence=[],
        )
        self.assertEqual(record1.id, record2.id)
        self.assertEqual(ExplainRecord.objects.count(), 1)


# ---------------------------------------------------------------------------
# View Tests
# ---------------------------------------------------------------------------


class ExplainDetailViewTest(TestCase):
    """Tests for the explain detail page."""

    def setUp(self):
        self.user = _setup_test_user()
        self.client = Client()
        self.client.login(email="e3test@example.com", password="testpass123")
        self.item = GuidanceItem.objects.create(
            user=self.user,
            title="Check weight",
            message="Your weight trend",
            priority=2,
            guidance_type="health_trend",
            source="sae_state",
            module="health",
            dedupe_key="test_view",
        )

    def test_detail_page_creates_on_demand(self):
        """Detail page creates explain record on demand."""
        url = f"/intelligence/explain/PGE/GuidanceItem/{self.item.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Why this intelligence?")
        self.assertContains(response, "Explanation")
        # Record should now exist
        self.assertEqual(ExplainRecord.objects.count(), 1)

    def test_detail_page_shows_existing_record(self):
        """Detail page shows existing record without creating new one."""
        ensure_explain_record(self.user, "PGE", self.item)
        self.assertEqual(ExplainRecord.objects.count(), 1)

        url = f"/intelligence/explain/PGE/GuidanceItem/{self.item.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExplainRecord.objects.count(), 1)

    def test_detail_page_other_user_404(self):
        """Other users cannot see explain records."""
        user2 = _setup_test_user(email="e3other@example.com")
        client2 = Client()
        client2.login(email="e3other@example.com", password="testpass123")
        url = f"/intelligence/explain/PGE/GuidanceItem/{self.item.pk}/"
        response = client2.get(url)
        self.assertEqual(response.status_code, 404)

    def test_detail_page_requires_login(self):
        """Unauthenticated users are redirected."""
        self.client.logout()
        url = f"/intelligence/explain/PGE/GuidanceItem/{self.item.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_detail_page_nonexistent_404(self):
        """Nonexistent object returns 404."""
        url = "/intelligence/explain/PGE/GuidanceItem/99999/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_briefing_explain_page(self):
        """Explain page works for DailyBriefing."""
        briefing = DailyBriefing.objects.create(
            user=self.user,
            briefing_date=date(2026, 2, 15),
            summary="Test briefing",
        )
        url = f"/intelligence/explain/DBE/DailyBriefing/{briefing.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DBE")

    def test_weekly_report_explain_page(self):
        """Explain page works for WeeklyIntelligenceReport."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Test report",
        )
        url = f"/intelligence/explain/WIRE/WeeklyIntelligenceReport/{report.pk}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WIRE")


# ---------------------------------------------------------------------------
# Why? Link Rendering Tests
# ---------------------------------------------------------------------------


class WhyLinkRenderingTest(TestCase):
    """Tests for 'Why?' link rendering on source pages."""

    def setUp(self):
        self.user = _setup_test_user()
        self.client = Client()
        self.client.login(email="e3test@example.com", password="testpass123")

    def test_guidance_inbox_has_why_link(self):
        """Guidance inbox renders 'Why?' link for each item."""
        GuidanceItem.objects.create(
            user=self.user,
            title="Test guidance",
            message="Test message",
            priority=3,
            guidance_type="test",
            source="sae_state",
            dedupe_key="test_why",
        )
        response = self.client.get("/guidance/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/intelligence/explain/PGE/GuidanceItem/")

    def test_weekly_report_detail_has_why_link(self):
        """Weekly report detail has 'Why?' link."""
        report = WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=date(2026, 2, 9),
            week_end_date=date(2026, 2, 15),
            summary="Test",
        )
        response = self.client.get(f"/intelligence/weekly/{report.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/intelligence/explain/WIRE/WeeklyIntelligenceReport/")


# ---------------------------------------------------------------------------
# Evidence Format Tests
# ---------------------------------------------------------------------------


class EvidenceFormatTest(TestCase):
    """Tests for evidence JSON format compliance."""

    def setUp(self):
        self.user = _setup_test_user()

    def test_evidence_has_required_fields(self):
        """Each evidence item has type, id, date, summary, url."""
        item = GuidanceItem.objects.create(
            user=self.user,
            title="Test",
            message="Msg",
            priority=3,
            guidance_type="test",
            source="sae_state",
            module="health",
            evidence={"data_points": [{"name": "weight", "value": 180}]},
            dedupe_key="test_format",
        )
        evidence = build_evidence_for_guidance(item)
        for e in evidence:
            self.assertIn("type", e)
            self.assertIn("summary", e)
            self.assertIn("url", e)
            # id and date can be None but must be present
            self.assertIn("id", e)
            self.assertIn("date", e)
