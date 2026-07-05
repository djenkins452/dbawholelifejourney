# ==============================================================================
# File: apps/ai/tests/test_health_critical_priority.py
# Description: EXECUTIVE JUDGMENT — health-critical, time-sensitive actions must
#   outrank routine/convenience/strategic items. Production failure: user "I'm feeling
#   great, lots of energy, sore from yesterday's workout" → Beth led with sleep/tasks/
#   France/shower/measurements and NEVER surfaced that morning prescription meds were
#   overdue. Root cause: no executive layer elevated it — interpret() read only tasks+
#   sleep+weight; the brief had no health-critical lead. General fix (not a medication
#   special-case): interpret() surfaces deterministic health-critical actions; the brief
#   LEADS with them and directs the action.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos.executive_interpretation import interpret, _health_critical_actions
from apps.ai.chatgpt_cos.executive_brief import compose_executive_brief

User = get_user_model()
_GDS = "apps.ai.cos_services.get_domain_state"
_DOSES = "apps.health.services.medicine_queries.MedicineQueries.today_doses"
OVERDUE = [{"medication": "Metformin", "time": "8:00 AM", "status": "overdue"},
           {"medication": "Lisinopril", "time": "8:00 AM", "status": "overdue"}]


def _empty(user, domain):
    return {"state": {}}


class HealthCriticalPriorityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="hc@test.com", password="x")

    def test_reader_surfaces_overdue_meds_deterministically(self):
        with mock.patch(_DOSES, return_value=OVERDUE):
            hc = _health_critical_actions(self.user)
        self.assertTrue(hc)
        self.assertEqual(hc[0]["kind"], "medication_overdue")
        self.assertIn("Metformin", hc[0]["text"])
        self.assertIn("overdue", hc[0]["text"].lower())

    def test_interpret_elevates_it_above_even_a_good_energy_report(self):
        # Even feeling great, overdue meds are the highest priority in the one picture.
        with mock.patch(_DOSES, return_value=OVERDUE), mock.patch(_GDS, side_effect=_empty):
            sig = interpret(self.user, subjective="positive")
        self.assertTrue(sig.health_critical)
        self.assertIn("highest priority", sig.executive_picture.lower())
        self.assertIn("overdue", sig.executive_picture.lower())

    def test_brief_leads_with_the_action_not_the_agenda(self):
        with mock.patch(_DOSES, return_value=OVERDUE), mock.patch(_GDS, side_effect=_empty):
            brief = compose_executive_brief(self.user, lead="Got it. ", subjective="positive")
        low = brief.lower()
        self.assertIn("before anything else", low)
        self.assertIn("overdue", low)
        self.assertIn("take care of that first", low)
        # It LEADS — appears at the very front, not buried in the agenda.
        self.assertLess(low.index("before anything else"), 40)

    def test_does_not_fire_when_nothing_is_health_critical(self):
        pending = [{"medication": "Metformin", "time": "8:00 PM", "status": "pending"}]
        with mock.patch(_DOSES, return_value=pending), mock.patch(_GDS, side_effect=_empty):
            sig = interpret(self.user, subjective="positive")
            brief = compose_executive_brief(self.user, subjective="positive")
        self.assertFalse(sig.health_critical)
        self.assertNotIn("before anything else", brief.lower())
