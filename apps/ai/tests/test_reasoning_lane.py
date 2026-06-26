# ==============================================================================
# File: apps/ai/tests/test_reasoning_lane.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reasoning Lane — health-scoped intents (no cross-domain contamination)
# ==============================================================================
"""
Validates the reasoning-lane framework + the health-scope contamination fix:

  Planner (structured plan) -> deterministic authoritative retrieval (health
  intents SCOPED to health truth) -> HealthWorkingMemoryCurator (health truth
  ONLY) -> one plain _call_api reasoning (+ deterministic health fallback).

Regression: health reasoning must NEVER receive tasks / generic decisions
(the "overdue Harley task" contamination).
"""

import contextlib
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.reasoning import answer_reasoning_question
from apps.ai.chatgpt_cos.reasoning.plan import (
    IMPLEMENTED_INTENTS,
    deterministic_health_intent,
    parse_plan,
)
from apps.ai.chatgpt_cos.reasoning.stages import (
    INTENT_CURATORS,
    REASONING_PROFILES,
    _calibrate_label,
    _health_concerns_fallback,
    _health_focus_today_fallback,
    _health_progress_fallback,
    _health_risk_fallback,
    _intra_day_hint,
    _nutrition_time_context,
    build_working_memory,
    health_working_memory,
    retrieve_truth,
    run_reasoning,
)

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_CALL_API_TOOLS = "apps.ai.services.ai_service._call_api_with_tools"
_BUILD_EXEC = "apps.core.execution.execution_state.build_execution_state"

# A CONTAMINATED plan (the planner mistakenly requests cross-domain truth) — the
# health scope must drop risk_decision/execution_decision before retrieval.
_RISK_PLAN_JSON = json.dumps({
    "intent": "biggest_health_risk", "response_mode": "reasoning",
    "domains": ["health"],
    "required_truth": ["risk_decision", "execution_decision", "health_state"],
    "optional_truth": ["foundational_health"], "reasoning_style": "risk_triage",
    "urgency": "high", "confidence": 0.9,
})
_PROGRESS_PLAN_JSON = json.dumps({
    "intent": "overall_progress", "response_mode": "mixed",
    "domains": ["health"],
    "required_truth": ["health_state", "foundational_health"],
    "optional_truth": [], "reasoning_style": "holistic_review",
    "urgency": "normal", "confidence": 0.85,
})
_OTHER_PLAN_JSON = json.dumps({"intent": "other", "response_mode": "lookup",
                               "domains": [], "required_truth": [],
                               "optional_truth": [], "reasoning_style": "",
                               "urgency": "low", "confidence": 0.5})

# A task-shaped decision — if this ever reaches health working memory, the test fails.
_TASK_DECISION = {"mode": "risk", "primary_action": {"type": "task",
                  "title": "Wake up", "source": "routine"},
                  "reason": "overdue", "message": "Biggest risk: Wake up."}

_HEALTH_STATE = {"status": "ready", "domain": "health", "state": {
    "weight_current": 298.3, "weight_unit": "lb", "weight_trend": "decreasing",
    "bp_systolic": 111, "bp_diastolic": 72, "sleep_avg_hours_7d": 6.7,
    "weight_goal": 240.0, "weight_goal_remaining": 58.3,
    "weight_goal_on_track": False, "plateau_risk_label": "Elevated",
    "_huge": list(range(100)),
}}


@contextlib.contextmanager
def _mock_providers():
    with mock.patch("apps.ai.cos_services.get_domain_state",
                    side_effect=lambda u, d: _HEALTH_STATE), \
         mock.patch("apps.ai.cos_services.get_foundational_health_facts",
                    return_value={"current_weight": {"value": 298.3, "unit": "lb"}}), \
         mock.patch(_BUILD_EXEC, return_value={}) as bes, \
         mock.patch("apps.core.execution.selectors.select",
                    return_value=_TASK_DECISION):
        yield bes


class PlanParsingTests(TestCase):
    def test_valid_plan(self):
        p = parse_plan(_RISK_PLAN_JSON)
        self.assertEqual(p.intent, "biggest_health_risk")

    def test_unknown_intent_becomes_other(self):
        self.assertEqual(parse_plan('{"intent":"x"}').intent, "other")

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_plan("not json"))


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class HealthScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_scope@example.com", password="x")

    def test_scope_drops_cross_domain_truth_and_never_fetches_it(self):
        plan = parse_plan(_RISK_PLAN_JSON)   # requests risk_decision + execution_decision
        with _mock_providers() as bes:
            truth = retrieve_truth(self.user, plan)
        # generic/cross-domain decisions DROPPED by the health scope:
        self.assertNotIn("risk_decision", truth)
        self.assertNotIn("execution_decision", truth)
        # health truth retained:
        self.assertIn("health_state", truth)
        self.assertIn("foundational_health", truth)
        # the decision engine was never even invoked:
        bes.assert_not_called()

    def test_health_working_memory_is_health_only(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        with _mock_providers():
            truth = retrieve_truth(self.user, plan)
        wm = build_working_memory(plan, truth)
        facts = wm["facts"]
        # curated health buckets present
        self.assertIn("current_status", facts)
        self.assertEqual(facts["current_status"]["bp_systolic"], 111)
        self.assertFalse(facts["goal_progress"]["weight_goal_on_track"])
        self.assertIn("ranked_concerns", facts)
        # NO contamination, NO raw SAE, NO raw enums/labels/source paths
        blob = json.dumps(wm, default=str)
        for forbidden in ("risk_decision", "Wake up", "routine", "_huge",
                          "active_risks", "plateau_risk_label", "Elevated",
                          "source"):
            self.assertNotIn(forbidden, blob)

    def test_curator_reads_only_health_truth(self):
        # even handed contaminated truth directly, the curator ignores non-health
        contaminated = {"health_state": _HEALTH_STATE,
                        "risk_decision": _TASK_DECISION}
        facts = health_working_memory(contaminated)
        self.assertNotIn("risk_decision", json.dumps(facts, default=str))
        self.assertNotIn("Wake up", json.dumps(facts, default=str))


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class ReasonerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_reason@example.com", password="x")

    def test_reasoning_uses_plain_call_api(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_health_risk",
              "facts": {"active_risks": {"weight_goal_on_track": False}}}
        with mock.patch(_CALL_API, return_value="Your BP needs attention.") as ca, \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertEqual(answer, "Your BP needs attention.")
        self.assertNotIn("tools", ca.call_args.kwargs)

    def test_health_fallback_uses_ranked_concerns(self):
        plan = parse_plan(_RISK_PLAN_JSON)
        wm = {"intent": "biggest_health_risk", "facts": {"ranked_concerns": [
            {"concern": "your weight-loss pace is a bit behind",
             "action": "a small, steady calorie adjustment"}]}}
        with mock.patch(_CALL_API, return_value=None):
            answer, fb = run_reasoning(self.user, "risk?", plan, wm)
        self.assertTrue(fb)
        self.assertIn("weight-loss pace", answer.lower())
        self.assertIn("next step", answer.lower())   # action included
        self.assertNotIn("wake up", answer.lower())


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_eng@example.com", password="x")

    def test_biggest_health_risk_no_contamination(self):
        # planner emits a CONTAMINATED plan; result must still be health-only.
        with _mock_providers(), \
             mock.patch(_CALL_API, side_effect=[_RISK_PLAN_JSON, None]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What is my biggest health risk right now?")
        self.assertEqual(out["reasoning"]["intent"], "biggest_health_risk")
        self.assertNotIn("risk_decision", out["reasoning"]["truth_keys"])
        self.assertNotIn("Wake up", out["answer"])
        self.assertNotIn("Harley", out["answer"])

    def test_overall_progress_end_to_end(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[_PROGRESS_PLAN_JSON, "You're behind on weight."]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "How am I doing overall with my health goals?")
        self.assertEqual(out["reasoning"]["intent"], "overall_progress")
        self.assertEqual(out["answer"], "You're behind on weight.")

    def test_other_intent_declines(self):
        with mock.patch(_CALL_API, return_value=_OTHER_PLAN_JSON):
            self.assertIsNone(answer_reasoning_question(self.user, "Tell a joke."))

    def test_planner_unavailable_declines_for_non_health(self):
        # planner None + a non-health question -> decline (no resilience match)
        with mock.patch(_CALL_API, return_value=None):
            self.assertIsNone(answer_reasoning_question(self.user, "what's the weather?"))


class ToneCalibrationTests(TestCase):  # Fix 3
    def test_severe_labels_softened(self):
        self.assertEqual(_calibrate_label("Significant"), "elevated — worth watching")
        self.assertEqual(_calibrate_label("Critical"), "worth attention")
        self.assertEqual(_calibrate_label("dangerous"), "worth watching")

    def test_non_severe_labels_unchanged(self):
        self.assertEqual(_calibrate_label("Elevated"), "Elevated")
        self.assertEqual(_calibrate_label("stable"), "stable")
        self.assertEqual(_calibrate_label(False), False)

    def test_raw_enum_never_leaks_to_model_facing_wm(self):
        truth = {"health_state": {"state": {
            "muscle_loss_risk_level": "MED", "weight_goal_on_track": False}}}
        facts = health_working_memory(truth)
        blob = json.dumps(facts, default=str)
        self.assertNotIn("MED", blob)                     # raw enum gone
        self.assertNotIn("muscle_loss_risk_level", blob)  # field name gone
        concerns = " ".join(c["concern"] for c in facts.get("ranked_concerns", []))
        self.assertIn("muscle", concerns.lower())         # surfaced as coaching

    def test_prompts_carry_calibration_and_no_alarmist_words(self):
        for intent in ("biggest_health_risk", "overall_progress",
                       "health_focus_today", "health_concerns"):
            sys = REASONING_PROFILES[intent]["system"].lower()
            self.assertIn("worth watching", sys)
            self.assertIn("evidence-based", sys)


class NutritionTimeAwarenessTests(TestCase):  # Fix 2
    def test_intra_day_hints(self):
        self.assertEqual(_intra_day_hint(0, 176, 40, "morning"),
                         "early_day_not_yet_logged")
        self.assertEqual(_intra_day_hint(20, 176, 40, "morning"),
                         "logging_in_progress")
        self.assertEqual(_intra_day_hint(0, 176, 40, "evening"),
                         "nothing_logged_today")
        self.assertEqual(_intra_day_hint(50, 176, 40, "evening"),
                         "below_typical_for_time_of_day")
        self.assertEqual(_intra_day_hint(150, 176, 40, "evening"),
                         "on_track_for_time_of_day")

    def test_nutrition_context_morning_zero_not_a_risk(self):
        from types import SimpleNamespace
        nut = {"daily_protein_g": 0.0, "rolling_7d_protein_avg": 176.9,
               "protein_target": 40.0, "daily_calories": 0.0,
               "rolling_7d_calories_avg": 1993.5, "calorie_target": 2000}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=nut), \
             mock.patch("apps.core.utils.get_user_now",
                        return_value=SimpleNamespace(hour=9)):
            ctx = _nutrition_time_context(object())
        self.assertEqual(ctx["day_phase"], "morning")
        self.assertEqual(ctx["protein_g"]["interpretation"],
                         "early_day_not_yet_logged")
        self.assertEqual(ctx["protein_g"]["typical_7d_avg"], 176.9)

    def test_curator_includes_nutrition_context_when_user_given(self):
        from types import SimpleNamespace
        nut = {"daily_protein_g": 0.0, "rolling_7d_protein_avg": 176.9,
               "protein_target": 40.0}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=nut), \
             mock.patch("apps.core.utils.get_user_now",
                        return_value=SimpleNamespace(hour=9)):
            facts = health_working_memory({"health_state": {"state": {}}},
                                          user=object())
        self.assertIn("nutrition_context", facts)


class RankedConcernsTests(TestCase):  # Fix #1 — protein over-anchoring
    def test_benign_labels_and_early_day_nutrition_excluded(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _rank_health_concerns
        buckets = {
            "active_risks": {"weight_goal_on_track": False,
                             "muscle_loss_risk_level": "LOW",
                             "glucose_variability_level": "stable"},
            "goal_progress": {"weight_goal_on_track": False},
            "nutrition_context": {"protein_g": {
                "interpretation": "early_day_not_yet_logged"}},
        }
        ranked = _rank_health_concerns(buckets)
        concerns = [c["concern"] for c in ranked]
        # only the genuine concern survives; protein (early-day) is excluded
        self.assertEqual(len(ranked), 1)
        self.assertIn("weight", concerns[0].lower())
        self.assertNotIn("protein", " ".join(concerns).lower())

    def test_real_risk_outranks_late_day_nutrition(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _rank_health_concerns
        buckets = {
            "active_risks": {"muscle_loss_risk_level": "elevated — worth watching"},
            "nutrition_context": {"protein_g": {
                "interpretation": "below_typical_for_time_of_day"}},
        }
        ranked = _rank_health_concerns(buckets)
        self.assertIn("muscle", ranked[0]["concern"].lower())   # outranks nutrition
        self.assertNotIn("MED", json.dumps(ranked))             # coaching, not enum

    def test_no_concerns_yields_empty(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _rank_health_concerns
        buckets = {"active_risks": {"muscle_loss_risk_level": "LOW"},
                   "goal_progress": {"weight_goal_on_track": True},
                   "nutrition_context": {"protein_g": {
                       "interpretation": "early_day_not_yet_logged"}}}
        self.assertEqual(_rank_health_concerns(buckets), [])


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class ReasoningGuaranteeTests(TestCase):  # Fix #2 — always answer, never fall through
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_guar@example.com", password="x")

    def test_deterministic_intent_matcher(self):
        from apps.ai.chatgpt_cos.reasoning.plan import deterministic_health_intent
        self.assertEqual(deterministic_health_intent(
            "How am I doing overall with my health goals?"), "overall_progress")
        self.assertEqual(deterministic_health_intent(
            "What should I focus on from a health perspective today?"),
            "health_focus_today")          # Phase 1: own intent, not lumped
        self.assertEqual(deterministic_health_intent(
            "What is my biggest health risk right now?"), "biggest_health_risk")
        self.assertIsNone(deterministic_health_intent("Tell me a joke."))

    def test_planner_none_health_question_still_answers(self):
        # planner _call_api returns None -> deterministic resilience -> answer
        with _mock_providers(), \
             mock.patch(_CALL_API, return_value=None), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "How am I doing overall with my health goals?")
        self.assertIsNotNone(out)                       # NOT None (no fall-through)
        self.assertEqual(out["reasoning"]["intent"], "overall_progress")
        self.assertTrue(out["answer"])                  # guaranteed non-empty
        self.assertTrue(out["reasoning"]["used_fallback"])

    def test_focus_question_routes_to_implemented_intent(self):
        # Phase 1: a "focus ... today" question now routes to its own intent
        # (health_focus_today), no longer lumped into biggest_health_risk.
        with _mock_providers(), \
             mock.patch(_CALL_API, return_value=None), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What should I focus on from a health perspective today?")
        self.assertEqual(out["reasoning"]["intent"], "health_focus_today")
        self.assertTrue(out["answer"])

    def test_non_health_still_declines_when_planner_none(self):
        with mock.patch(_CALL_API, return_value=None):
            self.assertIsNone(
                answer_reasoning_question(self.user, "Tell me a joke."))


class DeterministicFallbackQualityTests(TestCase):  # Fix #3
    def test_progress_fallback_multi_part(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _health_progress_fallback
        wm = {"facts": {
            "current_status": {"weight_current": 285.7, "weight_unit": "lb",
                               "latest_glucose": 133.0, "latest_glucose_unit": "mg/dL",
                               "sleep_avg_hours_7d": 6.7},
            "trends": {"weight_trend": "decreasing"},
            "goal_progress": {"weight_goal_remaining": 45.7},
            "ranked_concerns": [{"concern": "your weight-loss pace is a bit behind",
                                 "action": "x"}]}}
        ans = _health_progress_fallback(wm).lower()
        self.assertIn("weight", ans)
        self.assertIn("glucose", ans)
        self.assertIn("sleep", ans)
        self.assertIn("nudge", ans)            # next focus
        # not the degenerate single-fact answer
        self.assertGreater(len(ans), 60)

    def test_risk_fallback_has_concern_and_action(self):
        from apps.ai.chatgpt_cos.reasoning.stages import _health_risk_fallback
        wm = {"facts": {"ranked_concerns": [
            {"concern": "your blood sugar has been running high",
             "action": "a short walk after meals helps"}]}}
        ans = _health_risk_fallback(wm)
        self.assertIn("blood sugar", ans)
        self.assertIn("next step", ans.lower())


# Phase 1 — the four health intents must be intentionally differentiated.
# Enforces docs/BETH_HEALTH_INTENT_CONTRACTS.md (INV-1..INV-5).
_WM_MULTI = {"facts": {
    "current_status": {"weight_current": 285.7, "weight_unit": "lb",
                       "latest_glucose": 165, "sleep_avg_hours_7d": 6.1},
    "trends": {"weight_trend": "decreasing"},
    "goal_progress": {"weight_goal_remaining": 60},
    "nutrition_context": {"day_phase": "evening"},
    "ranked_concerns": [
        {"concern": "your blood sugar has been running high lately",
         "action": "a short walk after meals and steadier carb timing"},
        {"concern": "you've been averaging under 6.5 hours of sleep",
         "action": "protecting a consistent bedtime this week"},
    ],
}}

_VAGUE = ("keep improving", "work on", "stay active", "try to", "continue improving")


class Phase1IntentContractTests(TestCase):
    # --- registration / framework wiring ---
    def test_all_four_intents_have_profiles_and_curators(self):
        for intent in IMPLEMENTED_INTENTS:
            self.assertIn(intent, REASONING_PROFILES, intent)
            self.assertIn(intent, INTENT_CURATORS, intent)
        # The HEALTH quartet remains exactly as-is (byte-identical reference);
        # GOALS (domain #2) is additively registered alongside it.
        self.assertTrue({
            "biggest_health_risk", "overall_progress",
            "health_focus_today", "health_concerns"}.issubset(set(IMPLEMENTED_INTENTS)))
        self.assertTrue({
            "biggest_goal_risk", "goals_progress",
            "goals_focus_today", "goal_concerns"}.issubset(set(IMPLEMENTED_INTENTS)))

    # --- disambiguation (deterministic resilience matcher) ---
    def test_disambiguation_routes_four_intents(self):
        self.assertEqual(deterministic_health_intent(
            "What should I focus on from a health perspective today?"),
            "health_focus_today")
        self.assertEqual(deterministic_health_intent(
            "What are my health concerns?"), "health_concerns")
        self.assertEqual(deterministic_health_intent(
            "What is my biggest health risk right now?"), "biggest_health_risk")
        self.assertEqual(deterministic_health_intent(
            "How am I doing overall with my health goals?"), "overall_progress")

    # --- INV-1: concerns is a LIST (>=2); risk is a single item ---
    def test_inv1_concerns_list_vs_single_risk(self):
        concerns = _health_concerns_fallback(_WM_MULTI)
        risk = _health_risk_fallback(_WM_MULTI)
        self.assertIn("1.", concerns)
        self.assertIn("2.", concerns)            # >=2 items when >=2 exist
        self.assertNotIn("2.", risk)             # exactly one
        self.assertIn("blood sugar", risk)       # the TOP concern only

    # --- INV-2 + INV-5: focus_today = action + time + concrete, not vague ---
    def test_inv5_focus_today_concrete_action_three_parts(self):
        focus = _health_focus_today_fallback(_WM_MULTI)
        low = focus.lower()
        self.assertIn("today, focus on", low)              # (1) today's focus
        self.assertIn("one concrete step:", low)           # (3) concrete action
        self.assertTrue(any(k in low for k in (            # action is concrete
            "walk", "bedtime", "protein", "meal", "minute", "tonight")), focus)
        for v in _VAGUE:
            self.assertNotIn(v, low, f"vague phrase leaked: {v}")
        # INV-2: materially different from the single-risk answer
        self.assertNotEqual(focus, _health_risk_fallback(_WM_MULTI))

    def test_inv5_focus_today_action_when_no_concerns(self):
        focus = _health_focus_today_fallback({"facts": {}})
        self.assertIn("today", focus.lower())
        self.assertTrue(any(k in focus.lower() for k in ("walk", "step")), focus)

    # --- INV-3: progress is a multi-domain summary, not single-risk framing ---
    def test_inv3_progress_multidomain_not_single_risk(self):
        prog = _health_progress_fallback(_WM_MULTI).lower()
        self.assertIn("weight", prog)
        self.assertIn("glucose", prog)
        self.assertIn("sleep", prog)
        self.assertFalse(prog.startswith("the main thing worth your attention"))

    # --- INV-4: the four answers are pairwise distinct on one fixture ---
    def test_inv4_four_answers_pairwise_distinct(self):
        answers = {
            _health_risk_fallback(_WM_MULTI),
            _health_concerns_fallback(_WM_MULTI),
            _health_focus_today_fallback(_WM_MULTI),
            _health_progress_fallback(_WM_MULTI),
        }
        self.assertEqual(len(answers), 4)        # no two are identical


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class Phase1EndToEndTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rl_p1@example.com", password="x")

    def _plan_json(self, intent):
        return json.dumps({
            "intent": intent, "response_mode": "reasoning", "domains": ["health"],
            "required_truth": ["health_state", "foundational_health"],
            "optional_truth": [], "reasoning_style": "x",
            "urgency": "normal", "confidence": 0.8})

    def test_health_focus_today_end_to_end_health_only(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[self._plan_json("health_focus_today"), None]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What should I focus on health-wise today?")
        self.assertEqual(out["reasoning"]["intent"], "health_focus_today")
        self.assertNotIn("risk_decision", out["reasoning"]["truth_keys"])
        self.assertNotIn("Harley", out["answer"])
        self.assertTrue(out["answer"].strip())               # always answers

    def test_health_concerns_end_to_end_health_only(self):
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[self._plan_json("health_concerns"), None]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What are my health concerns?")
        self.assertEqual(out["reasoning"]["intent"], "health_concerns")
        self.assertNotIn("Harley", out["answer"])
        self.assertTrue(out["answer"].strip())

    def test_planner_misclassify_routes_deterministically(self):
        # planner returns 'other' for a clearly-implemented intent -> resilience
        with _mock_providers(), \
             mock.patch(_CALL_API,
                        side_effect=[_OTHER_PLAN_JSON, None]), \
             mock.patch(_CALL_API_TOOLS, side_effect=AssertionError("tools")):
            out = answer_reasoning_question(
                self.user, "What should I focus on health-wise today?")
        self.assertIsNotNone(out)
        self.assertEqual(out["reasoning"]["intent"], "health_focus_today")
