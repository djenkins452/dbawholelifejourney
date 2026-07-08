# ==============================================================================
# File: apps/ai/tests/test_conductor.py
# Description: THE CONDUCTOR — Step 1 (commit lifecycle). Verifies that every turn advances
#   the one unified conversation state (turn count, last act, active subject), that it runs
#   for every winning lane through route_message, and that it never raises. Step 1 is
#   record-only: it must NOT change which lane wins or what any answer says.
# ==============================================================================
from unittest import mock
import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos import conductor

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_NOW = "apps.core.utils.get_user_now"
_MORNING = datetime.datetime(2026, 7, 3, 9, 0, tzinfo=datetime.timezone.utc)


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class CommitTurnUnitTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("conductor@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def test_none_conversation_is_safe(self):
        conductor.commit_turn(None, winner="anything")     # must not raise

    def test_advances_turn_and_records_last_act(self):
        with mock.patch(_NOW, return_value=_MORNING):
            conductor.commit_turn(self.conv, winner="cos_briefing", user=self.u)
        st = conductor.read_turn_state(self.conv)
        self.assertEqual(st["turn"], 1)
        self.assertEqual(st["last_act"], "cos_briefing")
        self.assertIn("last_seen", st)

    def test_turn_increments_across_calls(self):
        conductor.commit_turn(self.conv, winner="a")
        conductor.commit_turn(self.conv, winner="b")
        conductor.commit_turn(self.conv, winner="c")
        st = conductor.read_turn_state(self.conv)
        self.assertEqual(st["turn"], 3)
        self.assertEqual(st["last_act"], "c")
        self.assertEqual([h["act"] for h in st["history"]], ["a", "b", "c"])

    def test_active_subject_extracted_from_result(self):
        conductor.commit_turn(self.conv, winner="foundational_facts",
                              result={"fact_key": "sleep_last_night", "answer": "x"})
        self.assertEqual(conductor.read_turn_state(self.conv)["active_subject_key"],
                         "sleep_last_night")

    def test_active_subject_from_active_subject_dict(self):
        conductor.commit_turn(self.conv, winner="conversation_checkin",
                              result={"active_subject": {"fact_key": "sleep_last_night"}})
        self.assertEqual(conductor.read_turn_state(self.conv)["active_subject_key"],
                         "sleep_last_night")

    def test_never_raises_on_bad_result(self):
        conductor.commit_turn(self.conv, winner="x", result="not-a-dict")   # no raise
        self.assertEqual(conductor.read_turn_state(self.conv)["turn"], 1)


class CommitLifecycleThroughRouterTests(TestCase):
    """Every winning turn through route_message advances the one state — no matter which
    lane owned it. Step 1 changes no answer, only records progression."""
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.u = _mkuser("conductorroute@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("no llm")), \
             mock.patch(_CT, side_effect=RuntimeError("no tools")), \
             mock.patch(_NOW, return_value=_MORNING):
            return route_message(self.u, msg, self.conv)

    def test_state_advances_every_winning_turn(self):
        r1 = self._route("Good morning")
        self.assertIsNotNone(r1)
        st1 = conductor.read_turn_state(self.conv)
        self.assertEqual(st1["turn"], 1)
        self.assertTrue(st1["last_act"])                 # a real owner was recorded

        r2 = self._route("Good morning")
        st2 = conductor.read_turn_state(self.conv)
        self.assertEqual(st2["turn"], 2)                 # advanced again
        self.assertTrue(st2["last_act"])
