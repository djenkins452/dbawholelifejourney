# ==============================================================================
# File: apps/ai/tests/test_response_coherence.py
# Description: RESPONSE COHERENCE VALIDATION. A finished response must never assert
#   two different "current" parts of day. Production case: at 8:16 PM Beth said
#   "Good evening…" then "…how are you feeling this morning?" — each fragment valid,
#   the completed response impossible. Every COMPOSED response (greeting, check-in,
#   executive summary, mission update) is re-grounded to the actual clock at the
#   single choke point (route_message) before it is presented. Validated on the REAL
#   routed path, not just the unit.
# ==============================================================================
from datetime import datetime, timezone as _tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos import response_coherence as rc

User = get_user_model()

MORN = datetime(2026, 7, 3, 8, 16, tzinfo=_tz.utc)
AFT = datetime(2026, 7, 3, 14, 16, tzinfo=_tz.utc)
EVE = datetime(2026, 7, 3, 20, 16, tzinfo=_tz.utc)

# The exact production check-in fragment (strong-sleep branch of _morning_checkin).
CHECKIN = ("Before we dive into today — how are you feeling this morning, and is "
           "there anything you want me to know first?")


class ResponseCoherenceUnitTests(SimpleTestCase):
    def test_the_production_case_evening_greeting_plus_morning_checkin(self):
        text = "Good evening, Danny. You slept about 4.8 hours last night. " + CHECKIN
        # Individually valid; together impossible → conflict detected.
        self.assertFalse(rc.is_coherent(text, rc.EVENING))
        fixed, issues = rc.repair(text, part=rc.EVENING)
        self.assertTrue(issues)
        self.assertTrue(rc.is_coherent(fixed, rc.EVENING))
        self.assertNotIn("this morning", fixed.lower())
        self.assertIn("this evening", fixed.lower())
        self.assertIn("good evening", fixed.lower())        # the correct part stays

    def test_wrong_greeting_is_regrounded(self):
        fixed, _ = rc.repair("Good morning, Danny.", part=rc.EVENING)
        self.assertEqual(fixed, "Good evening, Danny.")

    def test_matching_time_is_left_untouched(self):
        text = "Good evening, Danny. How are you feeling this evening?"
        self.assertTrue(rc.is_coherent(text, rc.EVENING))
        self.assertEqual(rc.repair(text, part=rc.EVENING)[0], text)

    def test_historical_and_scheduled_references_are_never_rewritten(self):
        # "last night" and a scheduled "this morning" (no wellbeing cue) are legitimate
        # references, NOT present-moment frames — they must survive verbatim at evening.
        for text in ("You slept about 6 hours last night.",
                     "Your 8am workout this morning is already done.",
                     "Your meeting this morning went long."):
            self.assertEqual(rc.repair(text, part=rc.EVENING)[0], text)
            self.assertTrue(rc.is_coherent(text, rc.EVENING))

    def test_afternoon_regrounding(self):
        fixed, _ = rc.repair("Good morning. How are you feeling this morning?",
                             part=rc.AFTERNOON)
        self.assertIn("good afternoon", fixed.lower())
        self.assertIn("this afternoon", fixed.lower())
        self.assertNotIn("morning", fixed.lower())


class ComposedFamilyCoherenceTests(SimpleTestCase):
    """Production-style: for EACH part of day and EACH composed-response family, a
    finished response is re-grounded to one coherent sense of time."""

    FAMILIES = {
        "greeting": "Good {wrong}, Danny.",
        "checkin": "Good {wrong}, Danny. How are you feeling this {wrong}?",
        "executive_summary": ("Good {wrong}. Looking at the whole picture, today is "
                              "manageable; this {wrong} you've still got two items."),
        "mission_update": ("Good {wrong} — big milestone hit. Enjoy your {wrong}; "
                           "we'll line up the next phase."),
    }

    def test_every_family_is_coherent_at_every_part(self):
        wrongs = {rc.MORNING: "evening", rc.AFTERNOON: "morning", rc.EVENING: "morning"}
        for part, wrong in wrongs.items():
            for family, template in self.FAMILIES.items():
                text = template.format(wrong=wrong)
                fixed, _ = rc.repair(text, part=part)
                self.assertTrue(
                    rc.is_coherent(fixed, part),
                    f"{family} @ {part} still incoherent: {fixed!r}")
                # the wrong part-of-day must be gone; the right one present
                self.assertNotIn(wrong, fixed.lower(),
                                 f"{family} @ {part}: stale '{wrong}' survived")
                self.assertIn(part, fixed.lower())


class RoutedCheckinCoherenceTests(TestCase):
    """The REAL routed path: a greeting at each part of day produces a check-in whose
    FINISHED text never mixes two parts of day."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="coherence@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _route_greeting(self, clock, greeting):
        from apps.ai.chatgpt_cos.lanes import route_message
        # Force the STRONG-sleep check-in branch (the one with "this morning"), so the
        # incoherence is actually reachable, independent of SAE data in the test.
        strong = (["You got about 4.8 hours of sleep last night — a bit short."],
                  True, {"key": "sleep_last_night", "value": 4.8})
        with mock.patch("apps.core.utils.get_user_now", return_value=clock), \
                mock.patch("apps.ai.chatgpt_cos.lanes._overnight_facts",
                           return_value=strong):
            return route_message(self.user, greeting, self.conv)

    def test_evening_greeting_never_says_this_morning(self):
        out = self._route_greeting(EVE, "Good evening")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("good evening", ans)
        self.assertNotIn("this morning", ans)          # the production bug — gone
        self.assertIn("this evening", ans)             # re-grounded
        self.assertTrue(rc.is_coherent(out["answer"], rc.EVENING))

    def test_afternoon_greeting_is_coherent(self):
        out = self._route_greeting(AFT, "Good afternoon")
        self.assertIsNotNone(out)
        self.assertNotIn("this morning", out["answer"].lower())
        self.assertTrue(rc.is_coherent(out["answer"], rc.AFTERNOON))

    def test_morning_greeting_stays_coherent(self):
        out = self._route_greeting(MORN, "Good morning")
        self.assertIsNotNone(out)
        ans = out["answer"].lower()
        self.assertIn("good morning", ans)
        self.assertIn("this morning", ans)             # correct at morning
        self.assertTrue(rc.is_coherent(out["answer"], rc.MORNING))
