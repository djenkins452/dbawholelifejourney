"""
Transformation Dashboard view tests.

Validates login required, authenticated access, SAE state authority, and tile config.
"""

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from apps.users.models import TermsAcceptance, User


def _create_test_user(email="dash_transform@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.health_enabled = True
    user.preferences.save()
    return user


class TestTransformationDashboardView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_test_user()
        self.url = reverse("dashboard:transformation")

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_authenticated_access(self):
        self.client.login(email="dash_transform@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_context_contains_transformation_state(self):
        """Dashboard must retrieve transformation state from SAE."""
        self.client.login(email="dash_transform@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # Context should have transformation key (from SAE)
        self.assertIn("transformation", response.context)
        # Should be a dict (SAE state format)
        self.assertIsInstance(response.context["transformation"], dict)

    def test_template_used(self):
        self.client.login(email="dash_transform@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "dashboard/transformation.html")


class TestTransformationChartDataView(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = _create_test_user("dash_chart@example.com")
        self.url = reverse("dashboard:transformation_chart_data")

    def test_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_returns_json(self):
        self.client.login(email="dash_chart@example.com", password="testpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")


class TestTransformationTileConfig(TestCase):
    def test_tile_registered_in_config(self):
        from apps.dashboard.services.config_service import TILE_DEFINITIONS

        self.assertIn("transformation", TILE_DEFINITIONS)
        tile = TILE_DEFINITIONS["transformation"]
        self.assertEqual(tile["id"], "transformation")
        self.assertEqual(tile["module_dependency"], "health_enabled")
        self.assertFalse(tile["default_visible"])  # Opt-in
