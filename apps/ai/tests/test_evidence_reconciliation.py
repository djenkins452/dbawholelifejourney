# ==============================================================================
# File: apps/ai/tests/test_evidence_reconciliation.py
# Description: Listening & Evidence Reconciliation (Layer 2). The user's OWN report is
#   EVIDENCE that must be reconciled with the objective read — not ignored. Origin:
#   Beth said "You slept about 6.4 hours." → user "I feel refreshed, 6.4 is good for
#   me." → Beth "The bigger challenge today is your energy." (ignored the report). Now
#   a short night the user says felt refreshing is NOT framed as an energy-management
#   day; a normal night the user says felt terrible IS.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos.executive_interpretation import (
    classify_subjective_energy, interpret)
from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief

User = get_user_model()

_GDS = "apps.ai.cos_services.get_domain_state"


def _state(hours):
    def _fake(user, domain):
        return {"state": {"sleep_last_night_hours": hours}} if domain == "health" \
            else {"state": {}}
    return _fake


class SubjectiveClassifierTests(SimpleTestCase):
    def test_positive_and_negative_and_none(self):
        self.assertEqual(classify_subjective_energy("I feel good and refreshed"), "positive")
        self.assertEqual(classify_subjective_energy("6.4 is good for me, feeling refreshed"), "positive")
        self.assertEqual(classify_subjective_energy("honestly exhausted and drained"), "negative")
        self.assertEqual(classify_subjective_energy("ok but pretty tired"), "negative")  # negatives win
        self.assertIsNone(classify_subjective_energy("what's on my calendar"))


class InterpretReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="recon@test.com", password="x")

    def _interpret(self, hours, subjective=None, low_energy=False):
        with mock.patch(_GDS, side_effect=_state(hours)):
            return interpret(self.user, low_energy=low_energy, subjective=subjective)

    def test_feels_better_than_expected_not_an_energy_day(self):
        # Short night (6.4h) but user feels refreshed → reconcile, do NOT assert energy.
        sig = self._interpret(6.4, subjective="positive")
        self.assertEqual(sig.reconciliation, "positive_over_debt")
        self.assertNotEqual(sig.primary_challenge, "energy")

    def test_feels_worse_than_expected_energy_from_the_report(self):
        # Normal night (7.5h) but user reports running low → energy challenge from the
        # SUBJECTIVE report, not the number.
        sig = self._interpret(7.5, subjective="negative")
        self.assertEqual(sig.reconciliation, "negative_no_debt")
        self.assertEqual(sig.primary_challenge, "energy")

    def test_confirms_low_reinforced(self):
        sig = self._interpret(6.4, subjective="negative")
        self.assertEqual(sig.reconciliation, "confirmed_low")
        self.assertEqual(sig.primary_challenge, "energy")

    def test_confirms_good_reinforced(self):
        sig = self._interpret(7.5, subjective="positive")
        self.assertEqual(sig.reconciliation, "confirmed_good")
        self.assertNotEqual(sig.primary_challenge, "energy")

    def test_no_subjective_preserves_existing_behavior(self):
        # Without a report, a short night is still an energy read (unchanged).
        sig = self._interpret(6.4)
        self.assertEqual(sig.reconciliation, "")
        self.assertEqual(sig.primary_challenge, "energy")


class ReconciliationBriefTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="reconbrief@test.com", password="x")

    def _brief(self, hours, subjective):
        with mock.patch(_GDS, side_effect=_state(hours)):
            return compose_executive_brief(self.user, lead="Got it. ",
                                           subjective=subjective).lower()

    def test_production_case_reconciles_and_never_asserts_energy(self):
        out = self._brief(6.4, "positive")
        self.assertIn("encouraging", out)
        self.assertIn("lived experience", out)
        # The production failure line must be gone.
        self.assertNotIn("bigger challenge today", out)
        self.assertNotIn("it's your energy", out)

    def test_feels_worse_leads_with_listening_then_energy(self):
        out = self._brief(7.5, "negative")
        self.assertIn("trust that over the number", out)
        self.assertTrue("energy" in out)


class RoutedReconciliationTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="reconroute@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def test_greeting_then_positive_feeling_reconciles(self):
        from datetime import datetime, timezone as tz
        from apps.ai.chatgpt_cos.lanes import route_message
        with mock.patch("apps.core.utils.get_user_now",
                        return_value=datetime(2026, 7, 4, 7, 30, tzinfo=tz.utc)), \
                mock.patch(_GDS, side_effect=_state(6.4)):
            route_message(self.user, "Good morning", self.conv)
            out = route_message(
                self.user,
                "I am feeling good. 6.4 hours of sleep is good for me and I am feeling refreshed.",
                self.conv)
        self.assertEqual(out["lane"], "conversation_brief")
        low = out["answer"].lower()
        self.assertIn("encouraging", low)
        self.assertNotIn("bigger challenge today", low)
