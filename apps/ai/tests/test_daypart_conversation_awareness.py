# ==============================================================================
# File: apps/ai/tests/test_daypart_conversation_awareness.py
# Description: DAYPART REASONING & CONVERSATION AWARENESS — the two production
#   failures this capability closes:
#     1. At bedtime, "How am I doing today?" produced a MORNING planning narrative
#        welded to a bedtime wind-down tail (incoherent). The executive brief now
#        holds a NIGHT 'close_out' stance and composes a reflective close-out.
#     2. "Look at the message you gave me" / "that's not what I meant" were read as
#        a plan change. They now route to the self-aware REPAIR path (feedback about
#        Beth's OWN prior turn), never a domain lane.
# ==============================================================================
from datetime import datetime, timezone as _tz
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos import executive_brief as eb
from apps.ai.chatgpt_cos import conversation_planner as cp

User = get_user_model()
_NOW = "apps.core.utils.get_user_now"
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
NIGHT = datetime(2026, 7, 3, 22, 30, tzinfo=_tz.utc)   # close_out stance
MORNING = datetime(2026, 7, 3, 8, 30, tzinfo=_tz.utc)  # plan stance


def _mkuser(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class BedtimeStanceTests(TestCase):
    def setUp(self):
        self.u = _mkuser("daypart_night@example.com")

    def test_bedtime_brief_is_a_close_out_not_a_morning_plan(self):
        with mock.patch(_NOW, return_value=NIGHT):
            brief = eb.compose_executive_brief(self.u).lower()
        # It reflects + rests …
        self.assertIn("rest", brief)
        self.assertTrue("looking back" in brief or "tomorrow" in brief)
        # … and it NEVER plans the day / uses the morning execution framings that made
        # the production answer incoherent at 10pm.
        for morning_frame in ("full but workable", "i'll count today as a win",
                              "count today a win", "genuinely needs you today",
                              "try to catch up"):
            self.assertNotIn(morning_frame, brief)

    def test_daytime_brief_is_unchanged_still_orients_the_day(self):
        # The close-out gate must NOT alter the daytime read.
        with mock.patch(_NOW, return_value=MORNING):
            brief = eb.compose_executive_brief(self.u).lower()
        self.assertNotIn("wind down and get some real rest", brief)


class MetaConversationalDetectorTests(SimpleTestCase):
    def test_reference_to_beths_prior_turn_is_recognized(self):
        for m in ("Look at the message you gave me.",
                  "Read your last response.",
                  "Go back and read your message.",
                  "Look at what you wrote.",
                  "Your last response was off."):
            self.assertTrue(cp.refers_to_prior_turn(m), m)
            self.assertTrue(cp.is_meta_conversational(m), m)

    def test_correction_of_understanding_is_recognized(self):
        for m in ("That's not what I meant.",
                  "You misunderstood me.",
                  "That wasn't my question.",
                  "You didn't answer my question.",
                  "You're missing my point."):
            self.assertTrue(cp.refers_to_prior_turn(m), m)
            self.assertTrue(cp.is_meta_conversational(m), m)

    def test_ordinary_requests_are_not_meta_conversational(self):
        # A fresh domain question / recall must NOT be stolen by the repair path.
        for m in ("How am I doing today?",
                  "What should I focus on?",
                  "Remind me what my weight was on 7/1.",
                  "What's on my calendar tomorrow?",
                  "Good morning."):
            self.assertFalse(cp.refers_to_prior_turn(m), m)


class MetaConversationalRoutingTests(TestCase):
    """The production case: 'Look at the message you gave me' after a prior Beth turn
    must reach the REPAIR lane, not a plan-change / domain lane."""
    def setUp(self):
        from apps.ai.models import AssistantConversation, AssistantMessage
        self.u = _mkuser("daypart_meta@example.com")
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)
        # A prior Beth turn exists to refer back to.
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant",
            content="Coming up today you have Drink Protein Shake at 6:45 AM.")

    def _route(self, msg):
        from apps.ai.chatgpt_cos.lanes import route_message
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")), \
             mock.patch(_NOW, return_value=MORNING):
            return route_message(self.u, msg, self.conv)

    def test_look_at_the_message_you_gave_me_routes_to_repair(self):
        res = self._route("Look at the message you gave me.")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "conversation_repair")

    def test_thats_not_what_i_meant_routes_to_repair(self):
        res = self._route("That's not what I meant.")
        self.assertIsNotNone(res)
        self.assertEqual(res["lane"], "conversation_repair")
