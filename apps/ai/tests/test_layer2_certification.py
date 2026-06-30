# ==============================================================================
# File: apps/ai/tests/test_layer2_certification.py
# Description: LAYER 2 CERTIFICATION GATE (Executive Reasoning). Permanent proof the
#   reasoning layer is intact and reasons OVER Layer 1 without modifying it. Four tiers:
#   SMOKE (capabilities wired), FULL (each engine behaves), DEEP (edge cases), and the
#   MANDATORY CONVERSATION tier (this week's production conversations succeed). Once
#   GREEN, Layer 2 is frozen and every future layer re-runs this gate. No OpenAI.
# ==============================================================================
from datetime import timedelta, datetime, time
from importlib import import_module

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.truth import certification as CERT
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, FoodEntry, GlucoseEntry
from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane, _referential_lane

User = get_user_model()


# ---------------------------------------------------------------------------
# SMOKE — the layer is wired and its boundary holds.
# ---------------------------------------------------------------------------
class Layer2SmokeTests(SimpleTestCase):
    def test_manifest_is_consistent(self):
        L2 = CERT.LAYER_2
        self.assertEqual(L2["name"], "Executive Reasoning")
        self.assertEqual(L2["number"], 2)
        self.assertEqual(CERT.LAYERS[2], L2)
        self.assertEqual(L2["acceptance_results"]["conversation"], "GREEN")  # mandatory tier

    def test_all_platform_modules_import(self):
        for mod in CERT.LAYER_2["platform_modules"]:
            import_module(mod)

    def test_certification_gate_includes_layer1_and_layer2(self):
        mods = CERT.certification_modules(2)
        self.assertIn("apps.core.tests.test_layer1_certification", mods)   # L1 re-run
        self.assertIn("apps.ai.tests.test_layer2_certification", mods)     # L2 self
        self.assertEqual(len(mods), len(set(mods)))                        # de-duplicated

    def test_layer1_remains_certified_and_frozen(self):
        # Layer 2 must never have demoted Layer 1.
        self.assertEqual(CERT.LAYER_1["status"], "certified")
        self.assertTrue(CERT.LAYER_1["frozen"])
        self.assertEqual(CERT.highest_certified_layer(), 2)


# ---------------------------------------------------------------------------
# FULL — each reusable reasoning engine behaves.
# ---------------------------------------------------------------------------
class Layer2FullTests(SimpleTestCase):
    def test_reasoning_confidence_weakest_link(self):
        from apps.ai.chatgpt_cos.reasoning.engines import reasoning_confidence
        self.assertEqual(reasoning_confidence("high", "low"), "low")

    def test_risk_reads_interpretation_never_invents(self):
        from apps.ai.chatgpt_cos.reasoning.engines import assess_risk
        self.assertEqual(assess_risk({"value": 400})["level"], "normal")      # no interp
        self.assertEqual(assess_risk({"interpretation": {"concern": True}})["level"],
                         "elevated")

    def test_comparison_semantics_declared_per_metric(self):
        from apps.ai.chatgpt_cos.conversation_object import comparison_semantics
        self.assertEqual(comparison_semantics("glucose")["strategy"], "average")
        self.assertEqual(comparison_semantics("steps")["strategy"], "running_total")

    def test_goal_evolution(self):
        from apps.ai.chatgpt_cos import conversation_object as CO
        prev = {"topic": "meals", "timeframe": "today", "goal": "review"}
        self.assertEqual(CO.evolve_goal(prev, "meals", "yesterday"), CO.GOAL_COMPARE)


# ---------------------------------------------------------------------------
# DEEP — reasoning consumes Layer 1 truth read-only, and edge cases hold.
# ---------------------------------------------------------------------------
class Layer2DeepTests(TestCase):
    def test_reasoning_does_not_mutate_the_layer1_fact(self):
        from apps.ai.chatgpt_cos.reasoning.engines import assess_risk
        fact = {"value": 240, "interpretation": {"concern": True, "advice": "x"}}
        before = dict(fact)
        assess_risk(fact)
        self.assertEqual(fact, before)        # Layer 2 never modifies Layer 1 truth

    def test_intent_fulfillment_meal_comparison_is_a_comparison(self):
        from apps.ai.chatgpt_cos.fulfillment import fulfill_meal_comparison
        out = fulfill_meal_comparison("Yesterday", {"lunch": ["Pizza"]},
                                      "Today", {"breakfast": ["Oatmeal"]})
        self.assertTrue(out and ("lunch" in out.lower() or "breakfast" in out.lower()))


# ---------------------------------------------------------------------------
# CONVERSATION (MANDATORY) — this week's production conversations succeed end to end.
# ---------------------------------------------------------------------------
class Layer2ConversationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="l2conv@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _turn(self, q):
        r = (_why_explainer_lane(self.user, q, self.conv)
             or _referential_lane(self.user, q, self.conv)
             or answer_foundational_fact(self.user, q))
        if r:
            record_last_answer(self.conv, r.get("lane", "foundational_facts"), r)
            self.conv.refresh_from_db()
        return r

    def test_glucose_anchor_does_not_drift(self):
        # "compared to my average" must anchor on the CURRENT reading, not yesterday.
        def at_noon(d):
            return timezone.make_aware(datetime.combine(d, time(12, 0)))
        GlucoseEntry.objects.create(user=self.user, value=160, unit="mg/dL",
                                    recorded_at=timezone.now())
        GlucoseEntry.objects.create(user=self.user, value=105, unit="mg/dL",
                                    recorded_at=at_noon(self.yest))
        for d in range(2, 7):
            GlucoseEntry.objects.create(user=self.user, value=140, unit="mg/dL",
                                        recorded_at=at_noon(self.today - timedelta(days=d)))
        self._turn("What is my BG?")
        self._turn("What about yesterday?")
        self._turn("Compared to today.")
        avg = self._turn("Compared to my average.")["answer"]
        self.assertIn("160", avg)                 # anchored on current reading
        self.assertNotIn("don't have", avg.lower())

    def test_meals_compare_returns_the_comparison(self):
        for nm, mt, d in [("Eggs", "breakfast", self.yest), ("Pizza", "lunch", self.yest),
                          ("Oatmeal", "breakfast", self.today)]:
            FoodEntry.objects.create(user=self.user, food_name=nm, meal_type=mt,
                                     logged_date=d, serving_size=1, quantity=1)
        self._turn("What did I eat today?")
        self._turn("What about yesterday?")
        ans = self._turn("Compared to today.")["answer"]
        self.assertIn("lunch", ans.lower())       # the comparison itself, not two lists

    def test_reasoning_answer_then_bare_why_stays_in_the_conversation(self):
        # Production blocker: "How am I doing overall?" (reasoning lane) → "Why?" returned
        # Assistant Unavailable, because bare "Why?" matched no follow-up cue and cascaded
        # to the planner. The reasoning answer IS recorded; bare "Why?" must resolve
        # deterministically from it — no leaving the executive-reasoning conversation.
        record_last_answer(self.conv, "personal_reasoning", {
            "answer": "Overall you're doing well — glucose stable, weight trending down.",
            "fast_path": "reasoning"})
        self.conv.refresh_from_db()
        out = _why_explainer_lane(self.user, "Why?", self.conv)
        self.assertIsNotNone(out)                          # was: declined → unavailable
        self.assertIn("doing well", out["answer"])         # explained from the prior answer

    def test_bare_why_does_not_swallow_a_real_reasoning_question(self):
        record_last_answer(self.conv, "personal_reasoning",
                           {"answer": "Overall you're doing well.", "fast_path": "reasoning"})
        self.conv.refresh_from_db()
        # A substantive "why" question is NOT a follow-up — it must cascade to the planner.
        self.assertIsNone(_why_explainer_lane(self.user, "Why did I gain weight?", self.conv))

    def test_steps_referential_and_recenter(self):
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        self._turn("How many steps today?")
        y = self._turn("What about yesterday?")["answer"]
        self.assertIn("8123", y)
        sub = self.conv.metadata["last_answer"]["active_subject"]["fact_key"]
        self.assertEqual(sub, "steps_yesterday")
        self._turn("Compared to today.")
        self.assertEqual(self.conv.metadata["last_answer"]["active_subject"]["fact_key"],
                         "steps_today")            # re-centered on current
