# ==============================================================================
# File: apps/ai/tests/test_p32_executive_brief.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P32 Executive Brief Composer — Chief-of-Staff PRESENCE, not just
#   correctness. Multi-turn, deterministic (OpenAI disabled): the briefing leads
#   with executive orientation (never tasks), the agenda comes LAST, repair OWNS
#   the miss (doesn't ask Danny to diagnose) and re-briefs, and a presence scorer
#   grades orientation/assessment/prioritization/synthesis/temporal/actionability/
#   agenda-ordering. Includes the EXACT production conversation.
# ==============================================================================
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import executive_brief as eb

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"


class ComposerStructureTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.u = User.objects.create_user(email="p32c@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()

    def test_brief_leads_with_orientation_not_tasks(self):
        brief = eb.compose_executive_brief(self.u)
        self.assertTrue(brief.strip())
        head = brief[:120].lower()
        # the FIRST thing is an executive read, never a task/agenda line
        self.assertFalse(head.startswith(("coming up", "drink", "shower", "next up")))
        self.assertTrue(any(k in head for k in (
            "looking at everything", "whole picture", "manageable", "today is")))

    def test_brief_is_one_narrative_no_headings(self):
        brief = eb.compose_executive_brief(self.u)
        self.assertNotIn("\n\n", brief)               # one coherent story
        low = brief.lower()
        for h in ("where things stand", "overall read:", "what matters today:",
                  "highest-leverage move:"):
            self.assertNotIn(h, low)

    def test_brief_is_deterministic_and_clean(self):
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")):
            brief = eb.compose_executive_brief(self.u)
        self.assertTrue(brief.strip())
        self.assertFalse(ar.is_failure_message(brief))
        self.assertEqual(ar.banned_hits(brief), [])

    def test_low_energy_frames_energy_as_challenge(self):
        brief = eb.compose_executive_brief(self.u, low_energy=True).lower()
        self.assertIn("it's your energy", brief)
        self.assertIn("matters more", brief)


class PresenceScorerTests(SimpleTestCase):
    GOOD = ("Looking at everything together, today is more manageable than it probably "
            "feels. The bigger challenge is your energy — you slept only about five "
            "hours, and that matters more than the open task count. Because of that, "
            "I wouldn't try to catch up on everything; if we protect your energy and "
            "handle the one thing due today, I'll count today a win. This afternoon "
            "you've still got a light workout.")
    BAD = ("Where things stand: strong. Overall read: a steady day. What matters today: "
           "tasks. Highest-leverage move: workout. Coming up today you have Drink "
           "Protein Shake at 6:45 AM.")

    def test_good_brief_scores_high(self):
        s = eb.score_executive_presence(self.GOOD)
        self.assertGreaterEqual(s["score"], 0.85)
        for d in ("no_report_headings", "synthesis", "explains_why", "judgment",
                  "conversational"):
            self.assertTrue(s[d], d)

    def test_report_dump_scores_low(self):
        s = eb.score_executive_presence(self.BAD)
        self.assertLess(s["score"], 0.5)
        self.assertFalse(s["no_report_headings"])   # visible headings -> fails
        self.assertFalse(s["temporal_ok"])          # "coming up" -> fails


class _Conv:
    """Helper to drive a real multi-turn conversation with OpenAI disabled."""
    def setup_user(self):
        from apps.users.models import TermsAcceptance
        from apps.ai.models import AssistantConversation
        self.u = User.objects.create_user(email="p32s@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.u, is_active=True)

    def say(self, msg):
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(conversation=self.conv, role="user", content=msg)
        with mock.patch(_C, side_effect=RuntimeError("openai down")), \
             mock.patch(_CT, side_effect=RuntimeError("openai down")):
            res = route_message(self.u, msg, self.conv)
        if res:
            AssistantMessage.objects.create(conversation=self.conv, role="assistant",
                                            content=res.get("answer") or "")
        return res


class ProductionConversationTests(_Conv, TestCase):
    def setUp(self):
        self.setup_user()

    def test_exact_production_conversation(self):
        # 1. Good morning -> check-in first (no task dump)
        r1 = self.say("Good morning")
        self.assertEqual(r1["lane"], "conversation_checkin")
        self.assertNotIn("coming up", r1["answer"].lower())

        # 2. I'm tired but okay -> EXECUTIVE brief (orientation first, recovery framing)
        r2 = self.say("I'm tired but okay")
        self.assertEqual(r2["lane"], "conversation_brief")
        s2 = eb.score_executive_presence(r2["answer"])
        self.assertTrue(s2["no_report_headings"], r2["answer"][:200])
        self.assertTrue(s2["synthesis"])
        self.assertIn("it's your energy", r2["answer"].lower())
        self.assertFalse(r2["answer"].lower().startswith(("coming up", "drink")))

        # 3. What do I need to know about today? -> executive composer again
        r3 = self.say("What do I need to know about today?")
        self.assertIsNotNone(r3)
        self.assertEqual(r3["lane"], "cos_briefing")
        self.assertTrue(eb.score_executive_presence(r3["answer"])["no_report_headings"])

        # 4-5. Critique -> self-aware REPAIR that re-briefs (no "tell me what's wrong")
        self.say("That didn't feel like a first-class Chief of Staff response.")
        r5 = self.say("Does that sound right to you?")
        self.assertEqual(r5["lane"], "conversation_repair")
        ans = r5["answer"].lower()
        self.assertIn("you're right", ans)                 # owns it
        self.assertNotIn("tell me exactly what", ans)       # does NOT ask Danny to diagnose
        self.assertNotIn("tell me what looked", ans)
        self.assertTrue(eb.score_executive_presence(r5["answer"])["no_report_headings"])  # re-briefs

    def test_repair_names_the_agenda_led_failure(self):
        from apps.ai.models import AssistantMessage
        AssistantMessage.objects.create(
            conversation=self.conv, role="assistant",
            content="Coming up today you have Drink Protein Shake at 6:45 AM. Shower.")
        r = self.say("that was not first class")
        self.assertEqual(r["lane"], "conversation_repair")
        self.assertIn("led with the agenda", r["answer"].lower())
