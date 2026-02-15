"""
Tests for Intelligence Command Center (ICC).

Verifies:
- Page loads correctly for authenticated users
- All 6 sections render (SAE, PGE, DBE, WIRE, DNE, PRIE)
- Permissions enforced (login required)
- Page renders gracefully with no engine data
- Page renders with engine data present
"""

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.users.models import TermsAcceptance, User


@override_settings(ROOT_URLCONF="config.urls")
class IntelligenceCommandCenterTests(TestCase):
    """Test the ICC page."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="icctest@example.com",
            password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.ai_enabled = True
        self.user.preferences.save()
        self.url = reverse("intelligence:command_center")

    def test_requires_login(self):
        """Anonymous users are redirected to login."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_page_loads_authenticated(self):
        """Authenticated users can access the ICC page."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_page_title(self):
        """Page title includes Intelligence."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertContains(response, "Intelligence Command Center")

    def test_all_sections_render(self):
        """All 6 sections render even with no data."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        content = response.content.decode()
        # Section IDs
        self.assertIn('id="icc-state"', content)
        self.assertIn('id="icc-guidance"', content)
        self.assertIn('id="icc-briefing"', content)
        self.assertIn('id="icc-weekly"', content)
        self.assertIn('id="icc-deliveries"', content)
        self.assertIn('id="icc-predictions"', content)

    def test_engine_labels_render(self):
        """Each section shows its engine label."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("SAE", content)
        self.assertIn("PGE", content)
        self.assertIn("DBE", content)
        self.assertIn("WIRE", content)
        self.assertIn("DNE", content)
        self.assertIn("PRIE", content)

    def test_empty_state_messages(self):
        """Empty state messages display when no data exists."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        content = response.content.decode()
        self.assertIn("No state snapshot yet", content)
        self.assertIn("No active guidance right now", content)
        self.assertIn("No briefing yet today", content)
        self.assertIn("No weekly report available yet", content)
        self.assertIn("No deliveries yet", content)
        self.assertIn("No active predictions", content)

    def test_context_has_app_name(self):
        """Context includes app_name for nav active state."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.context["app_name"], "intelligence")

    def test_context_has_help_context(self):
        """Context includes help_context_id."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(
            response.context["help_context_id"],
            "INTELLIGENCE_COMMAND_CENTER",
        )

    def test_guidance_section_with_data(self):
        """Guidance items render when present."""
        self.client.login(email="icctest@example.com", password="testpass123")
        from apps.core.ai_guidance.models import GuidanceItem

        GuidanceItem.objects.create(
            user=self.user,
            title="Test Guidance Item",
            message="You should drink more water based on recent trends.",
            priority=2,
            guidance_type="health_trend",
            source="pie_insight",
            module="health",
            dedupe_key="test-guidance-icc-1",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Test Guidance Item")
        self.assertEqual(response.context["guidance_count"], 1)

    def test_briefing_section_with_data(self):
        """Daily briefing renders when present."""
        self.client.login(email="icctest@example.com", password="testpass123")
        from apps.core.ai_briefing.models import DailyBriefing

        DailyBriefing.objects.create(
            user=self.user,
            briefing_date=timezone.now().date(),
            summary="Good morning! Here is your summary.",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Good morning! Here is your summary.")

    def test_weekly_report_section_with_data(self):
        """Weekly report renders when present."""
        self.client.login(email="icctest@example.com", password="testpass123")
        from apps.core.ai_weekly_report.models import WeeklyIntelligenceReport

        today = timezone.now().date()
        from datetime import timedelta
        week_start = today - timedelta(days=today.weekday())

        WeeklyIntelligenceReport.objects.create(
            user=self.user,
            week_start_date=week_start,
            week_end_date=week_start + timedelta(days=6),
            summary="This week you made great progress on your goals.",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "great progress")

    def test_delivery_section_with_data(self):
        """Delivery history renders when present."""
        self.client.login(email="icctest@example.com", password="testpass123")
        from apps.core.ai_delivery.models import DeliveredNotification

        DeliveredNotification.objects.create(
            user=self.user,
            source_engine="PGE",
            source_object_type="GuidanceItem",
            source_object_id=1,
            channel="in_app",
            title="Guidance Delivered",
            message="Check your guidance inbox.",
            status="sent",
            dedupe_hash=DeliveredNotification.compute_dedupe_hash(
                self.user.id, "in_app", "PGE", "GuidanceItem", 1
            ),
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Guidance Delivered")

    def test_prediction_section_with_data(self):
        """Predictions render when present."""
        self.client.login(email="icctest@example.com", password="testpass123")
        from apps.core.ai_predictions.models import Prediction

        Prediction.objects.create(
            user=self.user,
            prediction_type="weight_30d",
            module="health",
            predicted_value=175.0,
            predicted_date=timezone.now() + timezone.timedelta(days=30),
            confidence_score=0.72,
            explanation="Based on recent weight trends, projected weight in 30 days.",
            status="active",
            dedupe_key="test-prediction-icc-1",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "recent weight trends")

    def test_dashboard_back_link(self):
        """Page includes back link to dashboard."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertContains(response, reverse("dashboard:home"))

    def test_guidance_inbox_link(self):
        """Page includes link to guidance inbox."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertContains(response, "View All")

    def test_weekly_reports_link(self):
        """Page includes link to weekly reports."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertContains(response, "All Reports")

    def test_delivery_history_link(self):
        """Page includes link to delivery history."""
        self.client.login(email="icctest@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertContains(response, "Full History")
