"""View-layer tests for dashboard_v3.

Verifies:
  - /dashboard-v3/ renders 200 for an onboarded user.
  - Login is required (anonymous → redirect).
  - The dashboard_v2 route is unaffected (regression guard for isolation).
"""

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance, User


class DashboardV3ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3view@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email="v3view@test.com", password="testpass123")

    def test_home_renders_for_authenticated_user(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v3/home.html")

    def test_context_carries_v3_namespace(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn("v3", resp.context)
        self.assertIn("gauges", resp.context["v3"])
        self.assertIn("rhythm", resp.context["v3"])
        self.assertIn("executive_summary", resp.context["v3"])

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn(resp.status_code, (302, 301))

    def test_does_not_break_dashboard_v2(self):
        """Regression guard: V3 must not affect the V2 production route."""
        resp = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v2/home.html")
