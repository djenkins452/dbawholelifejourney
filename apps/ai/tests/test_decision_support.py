# ==============================================================================
# File: apps/ai/tests/test_decision_support.py
# Description: DECISION SUPPORT (Layer 2). When the user COMMUNICATES A DECISION —
#   abandoning a plan, reprioritizing, accepting a tradeoff, giving up, or calling it
#   a night — Beth must recognize the decision and help evaluate it, NOT retrieve
#   facts. Production failure: "I'm not going to work out or get to my protein drink.
#   I'm about done tonight. Just need to take my nightly meds and I am done." → Beth
#   listed medications. These regressions use the exact production conversations and
#   the REAL routed path (route_message), asserting the decision reaches decision
#   support (not the foundational fact lane) and the response reasons about the
#   tradeoff.
# ==============================================================================
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos import decision_support as ds

User = get_user_model()


class DecisionDetectionTests(SimpleTestCase):
    def test_the_production_message_is_a_decision_not_a_fact(self):
        msg = ("I'm not going to work out or get to my protein drink. I'm about done "
               "tonight. Just need to take my nightly meds and I am done.")
        sig = ds.detect_decision(msg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.kind, "abandon")
        self.assertIn("workout", sig.abandoned)
        self.assertIn("nutrition", sig.abandoned)
        self.assertIn("meds", sig.kept)          # "take my nightly meds" is KEPT
        self.assertNotIn("meds", sig.abandoned)

    def test_regression_phrases_all_recognized_as_decisions(self):
        for msg, kind in [
            ("I don't think I'm going to work out tonight.", "abandon"),
            ("I'm exhausted.", "fatigue"),
            ("I've changed my mind.", "change_mind"),
            ("I'm just going to bed.", "end_of_day"),
            ("I'm thinking about skipping church tomorrow.", "abandon"),
            ("I don't think I'll finish this goal.", "give_up_goal"),
            ("I think I'm done for today.", "end_of_day"),
        ]:
            sig = ds.detect_decision(msg)
            self.assertIsNotNone(sig, f"not recognized: {msg}")
            self.assertEqual(sig.kind, kind, f"{msg} -> {sig.kind}")

    def test_fact_questions_are_NOT_decisions(self):
        for msg in ("What medications do I take?", "What meds am I on?",
                    "Did I work out today?", "What's my protein target?",
                    "When is church tomorrow?", "How's my goal going?"):
            self.assertIsNone(ds.detect_decision(msg), f"false positive: {msg}")

    def test_situational_signals_read_from_recent_thread(self):
        sig = ds.detect_decision(
            "I'm not going to work out tonight.",
            recent_context="I've been out in the hot sun all day with friends and I'm tired.")
        self.assertTrue(sig.heat)
        self.assertTrue(sig.long_day)


class DecisionCompositionTests(SimpleTestCase):
    def _compose(self, signal):
        # Compose without touching the DB/interpret — assessment from signal only.
        with mock.patch.object(ds, "_safe_interpret",
                               return_value=_FakeSignals()):
            return ds.compose(signal, ds.assess(_FakeUser(), signal))

    def test_endorses_rest_with_personal_tiered_judgment(self):
        sig = ds.DecisionSignal(kind="abandon", abandoned=["workout", "nutrition"],
                                kept=["meds"], heat=True, long_day=True, fatigue=True,
                                active_day=True, activity="a day at the pool")
        out = self._compose(sig).lower()
        # 1) recognizes what was already accomplished today (not a nothing day)
        self.assertTrue("real day" in out or "not a day off" in out)
        self.assertIn("pool", out)
        # 2) recovery framed as a DELIBERATE strategy for the mission, not "doing less"
        self.assertIn("recovery", out)
        self.assertTrue("deliberate" in out and "mission" in out)
        # 3) meds are the NON-NEGOTIABLE (weighted above the rest), never listed out
        self.assertTrue("meds" in out and ("no matter what" in out or "nothing else" in out))
        # 4) effort-vs-benefit — the low-effort shake is elevated ABOVE the workout
        self.assertTrue("two minutes" in out and "effort" in out)
        pool_shake = out.index("two minutes")
        self.assertIn("workout", out)
        self.assertTrue(out.index("let the rest go") > pool_shake)   # shake ranked first
        # WHY throughout
        self.assertIn("—", out)

    def test_giving_up_a_goal_reflects_rather_than_endorsing(self):
        sig = ds.DecisionSignal(kind="give_up_goal", abandoned=["goal"])
        out = self._compose(sig).lower()
        self.assertIn("still", out)          # "still matters" / "still worth it"
        self.assertNotIn("optional thing", out)

    def test_dropping_meds_is_challenged(self):
        sig = ds.DecisionSignal(kind="abandon", abandoned=["meds", "workout"])
        out = self._compose(sig).lower()
        self.assertIn("meds", out)
        self.assertTrue("cost" in out or "protect" in out)   # gentle challenge, not endorsement


class _FakeSignals:
    recovery_needed = True
    sleep_hours = None
    strategic_focus = ""


class _FakeUser:
    id = 1


class RoutedDecisionSupportTests(TestCase):
    """The REAL routed path: a decision must reach decision_support BEFORE the
    foundational fact lane — so 'take my nightly meds and I'm done' is never a
    medication list."""

    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="decision@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _route(self, msg):
        # A voiced decision is claimed by decision_support (index 6) BEFORE any LLM
        # lane, so no OpenAI is needed.
        from apps.ai.chatgpt_cos.lanes import route_message
        return route_message(self.user, msg, self.conv)

    def test_production_case_routes_to_decision_support_not_facts(self):
        out = self._route("I'm not going to work out or get to my protein drink. "
                          "I'm about done tonight. Just need to take my nightly meds "
                          "and I am done.")
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "decision_support")
        ans = out["answer"].lower()
        # NOT a medication list; a tradeoff evaluation.
        self.assertNotIn("metformin", ans)
        self.assertTrue(any(w in ans for w in ("recovery", "rest", "tonight")))

    def test_fact_question_declined_by_decision_support(self):
        # Guard: decision support must DECLINE a real fact question so the fact lane
        # downstream can retrieve it. (Patching _foundational_lane can't prove routing
        # — LANE_REGISTRY captured the original reference — so assert the decline.)
        for fact in ("What medications do I take?", "Did I work out today?",
                     "What's my protein target?"):
            self.assertIsNone(ds.respond(self.user, fact, self.conv), fact)
