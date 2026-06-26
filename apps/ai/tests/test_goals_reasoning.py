# ==============================================================================
# File: apps/ai/tests/test_goals_reasoning.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Goals Reasoning Domain (Beth domain #2) — facts, curator, intent
#              quartet, deterministic fallbacks, routing, P25, and the health
#              non-regression (health stays byte-identical after generalization).
# ==============================================================================
"""Deterministic coverage for the Goals reasoning domain.

These tests exercise the DETERMINISTIC core only (no OpenAI): the curator, the
ranking, the four fallbacks, the deterministic intent matcher, plan synthesis,
foundational facts, and the P25 shadow classifier. They prove anti-collapse,
no-leakage, always-answer, correct routing, and that the dispatch generalization
left health behavior unchanged.
"""
import json
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod
from apps.ai.chatgpt_cos.reasoning import stages
from apps.ai.chatgpt_cos import foundational_facts as ff
from apps.ai.chatgpt_cos.p25_classifier import classify_request


# A realistic goals fixture: 2 overdue, 1 near deadline, 2 at-risk habits, low
# completion, over-commitment — exercises every concern band.
GOALS_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 7,
        "completion_rate": 0.32,
        "overdue_goal_count": 2,
        "days_to_next_deadline": 4,
        "next_deadline": "2026-06-30",
        "active_titles": [
            {"title": "Lose 20 lbs", "target_date": "2026-09-01", "is_foundational": True},
            {"title": "Write a book", "target_date": "2026-12-01", "is_foundational": False},
        ],
        "upcoming_titles": [{"title": "Finish chapter 3", "days_remaining": 4}],
        "overdue_titles": [
            {"title": "Launch side project", "days_overdue": 12},
            {"title": "Read 10 books", "days_overdue": 3},
        ],
        "mission": {"title": "Become a published author",
                    "momentum_score": 0.42, "next_milestone": {"id": 99}},
    }},
    "habits_state": {"state": {
        "active_habit_count": 5,
        "avg_completion_rate": 0.45,
        "longest_streak": 21,
        "streaks_per_habit": [
            {"name": "Morning pages", "current_streak": 3, "longest_streak": 21,
             "at_risk": True, "is_foundational": True, "frequency": "daily"},
            {"name": "Gym", "current_streak": 0, "longest_streak": 10,
             "at_risk": True, "is_foundational": False, "frequency": "weekly"},
        ],
    }},
}


def _wm(truth=None):
    truth = truth if truth is not None else GOALS_FIXTURE
    facts = stages.goals_working_memory(truth)
    return {"intent": "goal_concerns", "facts": facts}


# ---------------------------------------------------------------------------
# Registration / framework wiring
# ---------------------------------------------------------------------------
class GoalsRegistrationTests(SimpleTestCase):
    GOAL_INTENTS = ("biggest_goal_risk", "goals_progress",
                    "goals_focus_today", "goal_concerns")

    def test_intents_implemented(self):
        for i in self.GOAL_INTENTS:
            self.assertIn(i, planmod.IMPLEMENTED_INTENTS)

    def test_each_intent_has_curator_scope_and_profile(self):
        for i in self.GOAL_INTENTS:
            self.assertIs(stages.INTENT_CURATORS[i], stages.goals_working_memory)
            self.assertEqual(stages.INTENT_TRUTH_SCOPE[i], stages.GOALS_TRUTH)
            self.assertIn(i, stages.REASONING_PROFILES)
            self.assertIn("fallback", stages.REASONING_PROFILES[i])

    def test_goals_truth_scope_is_goals_only(self):
        self.assertEqual(stages.GOALS_TRUTH, frozenset({"goals_state", "habits_state"}))
        # No health truth can reach a goal intent (isolation / P11).
        self.assertNotIn("health_state", stages.GOALS_TRUTH)
        self.assertNotIn("foundational_health", stages.GOALS_TRUTH)

    def test_intent_domains_single_source(self):
        for i in self.GOAL_INTENTS:
            domain, truth = planmod.INTENT_DOMAINS[i]
            self.assertEqual(domain, "goals")
            self.assertEqual(set(truth), {"goals_state", "habits_state"})


# ---------------------------------------------------------------------------
# Curator — executive-clean, goals-only, no raw leakage
# ---------------------------------------------------------------------------
class GoalsCuratorTests(SimpleTestCase):
    def test_curator_surfaces_status_titles_mission_habits_concerns(self):
        facts = stages.goals_working_memory(GOALS_FIXTURE)
        self.assertEqual(facts["goal_status"]["active_goals"], 7)
        self.assertEqual(facts["goal_status"]["completion_pct"], 32)
        self.assertEqual(facts["goal_status"]["overdue_goals"], 2)
        self.assertIn("Lose 20 lbs", facts["active_goals"])
        self.assertEqual(facts["mission"], "Become a published author")
        self.assertEqual(facts["habits"]["active_habits"], 5)
        self.assertGreaterEqual(len(facts["ranked_concerns"]), 2)

    def test_curator_no_raw_internal_leakage(self):
        blob = json.dumps(stages.goals_working_memory(GOALS_FIXTURE))
        for forbidden in ("is_foundational", "momentum_score", "next_milestone",
                          "target_date", "2026-09-01", "frequency", "current_streak",
                          "days_overdue", "days_remaining", "SAE."):
            self.assertNotIn(forbidden, blob, f"leaked internal: {forbidden}")

    def test_curator_goals_only_ignores_other_domains(self):
        contaminated = dict(GOALS_FIXTURE)
        contaminated["health_state"] = {"state": {"weight_current": 199,
                                                   "latest_glucose": 250}}
        blob = json.dumps(stages.goals_working_memory(contaminated))
        self.assertNotIn("199", blob)
        self.assertNotIn("250", blob)
        self.assertNotIn("glucose", blob.lower())

    def test_curator_empty_truth_is_safe(self):
        self.assertEqual(stages.goals_working_memory({}), {})

    def test_ranking_orders_overdue_first(self):
        gs = GOALS_FIXTURE["goals_state"]["state"]
        hs = GOALS_FIXTURE["habits_state"]["state"]
        ranked = stages._rank_goal_concerns(gs, hs)
        self.assertIn("past their target date", ranked[0]["concern"])


# ---------------------------------------------------------------------------
# Intent quartet — anti-collapse (materially different) + INV invariants
# ---------------------------------------------------------------------------
class GoalsAntiCollapseTests(SimpleTestCase):
    def setUp(self):
        wm = _wm()
        self.risk = stages._goal_risk_fallback(wm)
        self.progress = stages._goals_progress_fallback(wm)
        self.concerns = stages._goal_concerns_fallback(wm)
        self.focus = stages._goals_focus_today_fallback(wm)

    def test_all_four_distinct(self):
        outs = [self.risk, self.progress, self.concerns, self.focus]
        self.assertEqual(len(set(outs)), 4, "intents collapsed to identical text")

    def test_inv1_risk_single_concerns_list(self):
        # risk: exactly one concern headline; concerns: a numbered list (>=2).
        self.assertNotIn("\n", self.risk)
        self.assertIn("2.", self.concerns)

    def test_inv2_focus_is_imperative_and_today(self):
        self.assertIn("today", self.focus.lower())
        self.assertNotEqual(self.focus, self.risk)

    def test_inv3_progress_is_multifield_summary(self):
        self.assertIn("active goal", self.progress.lower())
        # progress mentions completion / deadline / habits — not a single risk line
        self.assertTrue(any(k in self.progress.lower()
                            for k in ("%", "deadline", "follow-through", "target date")))

    def test_inv5_focus_ends_with_concrete_24h_action(self):
        self.assertIn("one concrete step", self.focus.lower())
        # concrete, not vague
        for vague in ("work on your goals", "make progress", "stay active"):
            self.assertNotIn(vague, self.focus.lower())


# ---------------------------------------------------------------------------
# Deterministic fallbacks — always answer, even with no data
# ---------------------------------------------------------------------------
class GoalsFallbackTests(SimpleTestCase):
    def test_all_fallbacks_answer_when_empty(self):
        empty = {"facts": {}}
        for fb in (stages._goal_risk_fallback, stages._goals_progress_fallback,
                   stages._goal_concerns_fallback, stages._goals_focus_today_fallback):
            out = fb(empty)
            self.assertTrue(out and isinstance(out, str))
            self.assertGreater(len(out), 20)

    def test_empty_is_honest_not_deflecting(self):
        empty = {"facts": {}}
        for fb in (stages._goal_risk_fallback, stages._goal_concerns_fallback):
            out = fb(empty).lower()
            # GB-5: never tell the user to go look it up elsewhere
            self.assertNotIn("dashboard", out)
            self.assertNotIn("go to", out)


# ---------------------------------------------------------------------------
# Routing — deterministic matcher + plan synthesis (health byte-identical)
# ---------------------------------------------------------------------------
class GoalsRoutingTests(SimpleTestCase):
    def test_goal_questions_route_to_goal_intents(self):
        cases = {
            "how am i doing on my goals": "goals_progress",
            "how are my goals tracking": "goals_progress",
            "what's my biggest goal risk": "biggest_goal_risk",
            "which goals are slipping": "goal_concerns",
            "what goal should i focus on today": "goals_focus_today",
        }
        for msg, intent in cases.items():
            self.assertEqual(planmod.deterministic_intent(msg), intent, msg)

    def test_health_routing_unchanged(self):
        # Health must remain byte-identical after the goal-signals-first change.
        cases = {
            "what is my biggest health risk": "biggest_health_risk",
            "what are my health concerns": "health_concerns",
            "what should i focus on today": "health_focus_today",
            "how am i doing": "overall_progress",
            "how am i doing with my health goals": "overall_progress",
        }
        for msg, intent in cases.items():
            self.assertEqual(planmod.deterministic_intent(msg), intent, msg)

    def test_alias_preserves_old_name(self):
        self.assertIs(planmod.deterministic_health_intent, planmod.deterministic_intent)
        self.assertIs(planmod.synthesize_health_plan, planmod.synthesize_plan)

    def test_non_reasoning_questions_return_none(self):
        for msg in ("what should i do next", "who was abraham lincoln", "thanks"):
            self.assertIsNone(planmod.deterministic_intent(msg), msg)

    def test_synthesize_plan_scopes_by_domain(self):
        gp = planmod.synthesize_plan("goals_progress")
        self.assertEqual(gp.domains, ["goals"])
        self.assertEqual(set(gp.required_truth), {"goals_state", "habits_state"})
        # health plan unchanged
        hp = planmod.synthesize_plan("biggest_health_risk")
        self.assertEqual(hp.domains, ["health"])
        self.assertEqual(set(hp.required_truth), {"health_state", "foundational_health"})


# ---------------------------------------------------------------------------
# Foundational facts — deterministic, always answer, canonical source
# ---------------------------------------------------------------------------
class GoalsFoundationalFactTests(SimpleTestCase):
    def test_classification(self):
        self.assertEqual(ff.classify_foundational_fact("how many goals do i have"),
                         "active_goal_count")
        self.assertEqual(ff.classify_foundational_fact("what's my top goal"), "top_goal")
        self.assertEqual(ff.classify_foundational_fact("any goals overdue"), "goals_overdue")
        self.assertEqual(ff.classify_foundational_fact("when's my next goal deadline"),
                         "next_goal_deadline")

    def test_reasoning_questions_are_not_facts(self):
        # These must fall through to the reasoning quartet, not the fact fast-path.
        for msg in ("what's my biggest goal risk", "which goals are slipping",
                    "how are my goals tracking"):
            self.assertNotIn(ff.classify_foundational_fact(msg), ff.GOAL_FACT_KEYS, msg)

    def test_format_sentences(self):
        self.assertEqual(
            ff.format_fact_sentence("active_goal_count", {"status": "ok", "value": 3}),
            "You have 3 active goal(s) right now.")
        self.assertIn("Become a published author", ff.format_fact_sentence(
            "top_goal", {"status": "ok", "value": "Become a published author"}))
        self.assertIn("don't have", ff.format_fact_sentence("top_goal", {"status": "unknown"}))

    def test_goal_facts_from_canonical_state(self):
        state = GOALS_FIXTURE["goals_state"]["state"]
        with patch("apps.core.ai_state.state_engine.get_module_state", return_value=state):
            facts = ff.get_foundational_goal_facts(object(),
                                                   ["active_goal_count", "top_goal",
                                                    "goals_overdue", "next_goal_deadline"])
        self.assertEqual(facts["active_goal_count"]["value"], 7)
        self.assertEqual(facts["top_goal"]["value"], "Become a published author")
        self.assertEqual(facts["goals_overdue"]["value"], 2)
        self.assertEqual(facts["next_goal_deadline"]["value"], 4)

    def test_goal_facts_safe_when_no_state(self):
        with patch("apps.core.ai_state.state_engine.get_module_state", return_value={}):
            facts = ff.get_foundational_goal_facts(object(),
                                                   ["active_goal_count", "top_goal"])
        self.assertEqual(facts["active_goal_count"]["status"], "unknown")
        self.assertEqual(facts["top_goal"]["status"], "unknown")


# ---------------------------------------------------------------------------
# P25 shadow — goal questions classify PERSONAL (routing stays shadow-only)
# ---------------------------------------------------------------------------
class GoalsP25Tests(SimpleTestCase):
    def test_goal_questions_classify_personal(self):
        for msg in ("how are my goals tracking", "how am i doing on my goals",
                    "what is my biggest goal risk"):
            r = classify_request(msg)
            self.assertEqual(r["classification"], "PERSONAL", f"{msg} -> {r}")

    def test_advice_shaped_goal_question_is_mixed(self):
        # advice + personal -> MIXED (personal goal truth grounds the answer);
        # still a PERSONAL-truth path, never EXTERNAL.
        r = classify_request("what goal should i focus on")
        self.assertIn(r["classification"], ("MIXED", "PERSONAL"))
        self.assertNotEqual(r["classification"], "EXTERNAL")

    def test_external_still_external(self):
        r = classify_request("who was abraham lincoln")
        self.assertEqual(r["classification"], "EXTERNAL")
