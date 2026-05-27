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

    def test_no_leaked_template_comments_in_rendered_page(self):
        """Render-time check: a Django {# #} block must never leak into
        the visible HTML. If this test fails, a multi-line {# #} block
        snuck in and is showing as page text."""
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        # The opening {# should never appear in rendered output.
        # (It's safe to assert exact-string absence — Django escapes
        # entities, so a real `{#` in HTML would have to come from a
        # broken-comment leak.)
        self.assertNotIn("{#", body, "Found a leaked Django comment in rendered HTML")
        self.assertNotIn("#}", body, "Found a leaked Django comment close in rendered HTML")

    def test_v2_dial_markup_renders_when_cockpit_has_domains(self):
        """When the user has active LifeGoals/HabitGoals, the v3 gauges
        section MUST render the canonical v2 cockpit_dial.html partial —
        not the v3 fallback tiles. This test seeds a LifeDomain + LifeGoal
        so the cockpit returns data and asserts the v2 dial markup
        appears in the rendered HTML."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain, _ = LifeDomain.objects.get_or_create(
            slug="health",
            defaults={
                "name": "Health",
                "color": "#dc2626",
                "is_active": True,
                "sort_order": 1,
            },
        )
        LifeGoal.objects.create(
            user=self.user,
            domain=domain,
            title="Test goal for gauges",
            status="active",
        )

        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        # Canonical v2 dial markers — if these aren't present, the gauges
        # aren't really rendering (regression we hit repeatedly).
        self.assertIn("v2-cockpit-dial", body)
        self.assertIn("v2-gauge-svg", body)
        self.assertIn("v2-dial-label", body)
