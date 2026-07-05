# ==============================================================================
# File: apps/ai/tests/test_executive_prioritization.py
# Description: EXECUTIVE PRIORITIZATION / significance ranking. Reported evidence that
#   MATERIALLY changes today's picture (making up two missed workouts) must become
#   today's HEADLINE and reorganize the recommendation — not be acknowledged then
#   demoted to a side note behind France 2027 / backlog / bike ride. And when
#   challenged, Beth must name the EXECUTIVE mistake, not merely apologize.
# ==============================================================================
from datetime import date, datetime, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.chatgpt_cos import conversation_planner as cp
from apps.ai.chatgpt_cos import executive_evidence as ev
from apps.ai.chatgpt_cos.executive_interpretation import interpret
from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"
_GDS = "apps.ai.cos_services.get_domain_state"
ACC = "made up 2 missed workouts (Wednesday, Friday)"


def _state(h):
    def f(user, domain):
        return {"state": {"sleep_last_night_hours": h}} if domain == "health" else {"state": {}}
    return f


class ExecutivePrioritizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="prio@test.com", password="x")
        cache.clear()

    def test_accomplishment_becomes_todays_headline_and_picture(self):
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(6.4)):
            ev.record_accomplishment(self.user, ACC)
            sig = interpret(self.user)
        # headline = the significant FACT
        self.assertIn("made up 2 missed workouts", sig.headline)
        self.assertIn("ahead of plan", sig.headline.lower())
        # executive_picture = the reasoned CONCLUSION (lives in interpret(), not the prompt)
        self.assertIn("recovery", sig.executive_picture.lower())
        self.assertIn("highest-leverage", sig.executive_picture.lower())

    def test_prompt_presents_the_read_declaratively_not_procedurally(self):
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(6.4)):
            ev.record_accomplishment(self.user, ACC)
            inj = format_cos_system_injection({"_user": self.user, "user_id": self.user.id})
        low = inj.lower()
        # Presents interpret()'s headline + picture …
        self.assertIn("today's executive headline", low)
        self.assertIn("made up 2 missed workouts", inj)
        self.assertIn("today's executive picture", low)
        self.assertIn("highest-leverage", low)
        # … and does NOT carry reasoning as procedural prompt rules.
        self.assertNotIn("build your response around", low)
        self.assertNotIn("is secondary", low)
        self.assertNotIn("did you not read", low)

    def test_challenge_is_recognized(self):
        for m in ("Did you not read my response?", "You missed what I told you",
                  "did you even read that"):
            self.assertTrue(cp.is_critique(m), m)

    def test_repair_names_the_executive_mistake_not_generic_remorse(self):
        from apps.ai.chatgpt_cos.lanes import _repair_response
        with mock.patch(_TODAY, return_value=TODAY), mock.patch(_GDS, side_effect=_state(6.4)):
            ev.record_accomplishment(self.user, ACC)
            out = _repair_response(
                self.user, "Did you not read my response?",
                "You slept 6.4 hours. France 2027 is overdue; here's tomorrow.")
        low = out["answer"].lower()
        self.assertIn("exactly what i missed", low)
        self.assertIn("made up 2 missed workouts", out["answer"])
        self.assertIn("headline", low)
        self.assertNotIn("let me own that", low)          # not the generic path

    def test_full_routed_report_then_challenge(self):
        from apps.ai.models import AssistantConversation, AssistantMessage
        from apps.ai.chatgpt_cos.lanes import route_message
        conv = AssistantConversation.objects.create(user=self.user)
        clock = datetime(2026, 7, 4, 19, 0, tzinfo=_tz.utc)
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now", return_value=clock), \
                mock.patch(_GDS, side_effect=_state(6.4)):
            r = route_message(self.user,
                              "I made up my workouts from Wednesday and Friday", conv)
            self.assertEqual(r["lane"], "accomplishment")
            AssistantMessage.objects.create(
                conversation=conv, role="assistant",
                content="You slept 6.4 hours. France 2027 is overdue.")
            out = route_message(self.user, "Did you not read my response?", conv)
        self.assertEqual(out["lane"], "conversation_repair")
        self.assertIn("made up 2 missed workouts", out["answer"])
