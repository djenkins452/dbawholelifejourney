"""
Onboarding Wizard Tests

Tests for the step-by-step onboarding wizard flow.

Location: apps/users/tests/test_onboarding_wizard.py
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings

from apps.users.models import TermsAcceptance
from apps.users.views import ONBOARDING_STEPS

User = get_user_model()


class OnboardingWizardStepsTest(TestCase):
    """Tests for the ONBOARDING_STEPS configuration."""

    def test_steps_have_required_fields(self):
        """Each step has id, title, and description."""
        for step in ONBOARDING_STEPS:
            self.assertIn("id", step)
            self.assertIn("title", step)
            self.assertIn("description", step)

    def test_welcome_is_first_step(self):
        """Welcome step is first."""
        self.assertEqual(ONBOARDING_STEPS[0]["id"], "welcome")

    def test_complete_is_last_step(self):
        """Complete step is last."""
        self.assertEqual(ONBOARDING_STEPS[-1]["id"], "complete")

    def test_expected_step_order(self):
        """Steps are in the expected order."""
        step_ids = [step["id"] for step in ONBOARDING_STEPS]
        expected = ["welcome", "theme", "modules", "ai", "location", "complete"]
        self.assertEqual(step_ids, expected)


class OnboardingWizardViewTest(TestCase):
    """Tests for the OnboardingWizardView."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        # Accept terms so we can access the wizard
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )
        self.client.login(email="test@example.com", password="testpass123")

    def test_wizard_requires_login(self):
        """Wizard requires authentication."""
        self.client.logout()
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertEqual(response.status_code, 302)

    def test_wizard_start_loads(self):
        """Wizard start page loads successfully."""
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertEqual(response.status_code, 200)

    def test_wizard_shows_welcome_step_by_default(self):
        """Default step is welcome."""
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertEqual(response.context["current_step"]["id"], "welcome")

    def test_wizard_step_theme_loads(self):
        """Theme step loads correctly."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "theme")
        self.assertIn("themes", response.context)

    def test_wizard_step_modules_loads(self):
        """Modules step loads correctly."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "modules"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "modules")
        self.assertIn("modules", response.context)

    def test_wizard_step_ai_loads(self):
        """AI step loads correctly."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "ai"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "ai")

    def test_wizard_step_location_loads(self):
        """Location step loads correctly."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "location"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "location")
        self.assertIn("timezone_choices", response.context)

    def test_wizard_step_complete_loads(self):
        """Complete step loads correctly."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "complete"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "complete")
        self.assertIn("summary", response.context)

    def test_wizard_progress_calculation(self):
        """Progress percentage is calculated correctly."""
        # Welcome (step 0) = 0%
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertEqual(response.context["progress_percent"], 0)

        # Complete (step 5) = 100%
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "complete"})
        )
        self.assertEqual(response.context["progress_percent"], 100)

    def test_invalid_step_defaults_to_welcome(self):
        """Invalid step ID defaults to welcome."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "invalid"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_step"]["id"], "welcome")


class OnboardingWizardSubmissionTest(TestCase):
    """Tests for wizard form submissions."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )
        self.client.login(email="test@example.com", password="testpass123")

    def test_welcome_step_advances_to_theme(self):
        """Submitting welcome step advances to theme."""
        response = self.client.post(
            reverse("users:onboarding_wizard"),
            {"action": "next"}
        )
        self.assertRedirects(
            response,
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"})
        )

    def test_theme_selection_saves(self):
        """Theme selection is saved to preferences."""
        self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"}),
            {"theme": "faith", "action": "next"}
        )
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.theme, "faith")

    def test_modules_selection_saves(self):
        """Module toggles are saved correctly."""
        self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "modules"}),
            {
                "journal_enabled": "on",
                "faith_enabled": "",  # Off
                "health_enabled": "on",
                "life_enabled": "on",
                "purpose_enabled": "",  # Off
                "action": "next"
            }
        )
        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.journal_enabled)
        self.assertFalse(self.user.preferences.faith_enabled)
        self.assertTrue(self.user.preferences.health_enabled)
        self.assertTrue(self.user.preferences.life_enabled)
        self.assertFalse(self.user.preferences.purpose_enabled)

    def test_ai_settings_save(self):
        """AI settings are saved correctly."""
        self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "ai"}),
            {
                "ai_enabled": "on",
                "ai_coaching_style": "direct",
                "action": "next"
            }
        )
        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.ai_enabled)
        self.assertEqual(self.user.preferences.ai_coaching_style, "direct")

    def test_location_settings_save(self):
        """Location settings are saved correctly."""
        self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "location"}),
            {
                "timezone": "America/New_York",
                "location_city": "Nashville",
                "location_country": "Tennessee, US",
                "action": "next"
            }
        )
        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.timezone, "America/New_York")
        self.assertEqual(self.user.preferences.location_city, "Nashville")
        self.assertEqual(self.user.preferences.location_country, "Tennessee, US")

    def test_complete_step_marks_onboarding_done(self):
        """Completing wizard marks onboarding as complete."""
        self.assertFalse(self.user.preferences.has_completed_onboarding)

        response = self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "complete"}),
            {"action": "complete"}
        )

        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.has_completed_onboarding)
        self.assertRedirects(response, reverse("dashboard:home"))

    def test_skip_action_advances_without_saving(self):
        """Skip action advances to next step without changing values."""
        original_theme = self.user.preferences.theme

        self.client.post(
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"}),
            {"action": "skip"}
        )

        self.user.preferences.refresh_from_db()
        self.assertEqual(self.user.preferences.theme, original_theme)


class OnboardingWizardNavigationTest(TestCase):
    """Tests for wizard navigation."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )
        self.client.login(email="test@example.com", password="testpass123")

    def test_prev_step_context_on_non_first_step(self):
        """Previous step is in context for non-first steps."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"})
        )
        self.assertIn("prev_step", response.context)
        self.assertEqual(response.context["prev_step"]["id"], "welcome")

    def test_no_prev_step_on_welcome(self):
        """No previous step on welcome page."""
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertIsNone(response.context.get("prev_step"))

    def test_next_step_context_on_non_last_step(self):
        """Next step is in context for non-last steps."""
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertIn("next_step", response.context)
        self.assertEqual(response.context["next_step"]["id"], "theme")

    def test_no_next_step_on_complete(self):
        """No next step on complete page."""
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "complete"})
        )
        self.assertIsNone(response.context.get("next_step"))


class OnboardingLegacyRedirectTest(TestCase):
    """Tests for legacy onboarding URL redirect."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )
        self.client.login(email="test@example.com", password="testpass123")

    def test_legacy_onboarding_redirects_to_wizard(self):
        """Legacy /onboarding/ URL redirects to wizard."""
        response = self.client.get(reverse("users:onboarding"))
        self.assertRedirects(response, reverse("users:onboarding_wizard"))


class OnboardingMiddlewareTest(TestCase):
    """Tests for middleware enforcement of onboarding completion."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        # Accept terms
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        )

    def test_incomplete_onboarding_redirects_to_wizard(self):
        """User with incomplete onboarding is redirected to wizard."""
        self.user.preferences.has_completed_onboarding = False
        self.user.preferences.save()
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(reverse("dashboard:home"))
        self.assertRedirects(response, reverse("users:onboarding_wizard"))

    def test_complete_onboarding_allows_access(self):
        """User with completed onboarding can access dashboard."""
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)

    def test_onboarding_pages_accessible_during_onboarding(self):
        """Onboarding pages are accessible when onboarding is incomplete."""
        self.user.preferences.has_completed_onboarding = False
        self.user.preferences.save()
        self.client.login(email="test@example.com", password="testpass123")

        # Wizard start page
        response = self.client.get(reverse("users:onboarding_wizard"))
        self.assertEqual(response.status_code, 200)

        # Wizard step pages
        response = self.client.get(
            reverse("users:onboarding_wizard_step", kwargs={"step": "theme"})
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_exempt_from_onboarding(self):
        """Admin pages are exempt from onboarding check."""
        self.user.preferences.has_completed_onboarding = False
        self.user.preferences.save()
        self.user.is_staff = True
        self.user.save()
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get("/admin/")
        # Should not redirect to onboarding (might redirect to admin login)
        self.assertNotEqual(response.url if response.status_code == 302 else "",
                          reverse("users:onboarding_wizard"))
