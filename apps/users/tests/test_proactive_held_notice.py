# ==============================================================================
# File: apps/users/tests/test_proactive_held_notice.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A paused platform says so; it never looks broken or silently flips a choice
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-14
# ==============================================================================
"""On 2026-09-14 the preferences page showed "Let it start things on its own" checked while
the operator hold refused every proactive attempt. The person read a promise; the platform
was keeping a decision. The two must never look the same.

The notice reads from the SAME authority the admission seam evaluates, and the checkbox
stays the person's own — the gate never toggles it.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

NOTICE = "Proactive assistance is temporarily paused by Whole Life Journey"


class ProactiveHeldNoticeTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="held-ui@contract.test", password="pw")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.prefs = self.user.preferences
        self.prefs.has_completed_onboarding = True
        self.prefs.save()
        self.client.force_login(self.user)

    def _page(self, *, preference_on, gate_on):
        self.prefs.proactive_assistance_enabled = preference_on
        self.prefs.save()
        with mock.patch("apps.ai.llm_admission.proactive_ai_enabled", return_value=gate_on):
            return self.client.get(reverse("users:preferences"))

    def test_preference_on_and_gate_off_shows_the_notice(self):
        response = self._page(preference_on=True, gate_on=False)
        self.assertContains(response, NOTICE)
        self.assertContains(response, "Your preference is saved")

    def test_gate_on_shows_no_notice(self):
        response = self._page(preference_on=True, gate_on=True)
        self.assertNotContains(response, NOTICE)

    def test_preference_off_shows_no_notice_whatever_the_gate(self):
        for gate in (True, False):
            self.assertNotContains(self._page(preference_on=False, gate_on=gate), NOTICE)

    def test_the_checkbox_stays_checked_while_held(self):
        """The gate never silently changes the person's choice."""
        response = self._page(preference_on=True, gate_on=False)
        self.assertContains(
            response,
            'name="proactive_assistance_enabled"\n'
            '                                                   id="proactive_assistance_enabled"\n'
            '                                                   checked',
            html=False)
        self.prefs.refresh_from_db()
        self.assertTrue(self.prefs.proactive_assistance_enabled)

    def test_the_notice_reads_the_admission_authority_not_behaviour(self):
        import inspect

        from apps.users import views
        src = inspect.getsource(views.PreferencesView.get_context_data)
        self.assertIn("proactive_ai_enabled()", src)

    def test_a_gate_read_failure_never_breaks_the_page(self):
        self.prefs.proactive_assistance_enabled = True
        self.prefs.save()
        with mock.patch("apps.ai.llm_admission.proactive_ai_enabled",
                        side_effect=RuntimeError("settings unavailable")):
            response = self.client.get(reverse("users:preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, NOTICE)
