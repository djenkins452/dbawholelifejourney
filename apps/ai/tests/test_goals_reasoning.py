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

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod
from apps.ai.chatgpt_cos.reasoning import stages
from apps.ai.chatgpt_cos import foundational_facts as ff
from apps.ai.chatgpt_cos.p25_classifier import classify_request

User = get_user_model()


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
            {"title": "Lose 20 lbs", "target_date": "2026-09-01", "is_foundational": True,
             "evidence": {"momentum": "strong", "trend": "rising",
                          "phase": "Cutting phase", "momentum_summary": "strong momentum and building",
                          "success_drivers": ["weight trending down"], "risk_drivers": [],
                          "recommended_action": "keep your current routine going and log today's progress",
                          "as_of": "2026-06-25"}},
            {"title": "Write a book", "target_date": "2026-12-01", "is_foundational": False,
             "evidence": {"momentum": "moderate", "trend": "stable",
                          "phase": "Drafting", "momentum_summary": "steady momentum",
                          "success_drivers": ["2 milestones completed"], "risk_drivers": [],
                          "recommended_action": "take the next concrete step toward \"Drafting\"",
                          "as_of": "2026-06-25"}},
        ],
        "upcoming_titles": [{"title": "Finish chapter 3", "days_remaining": 4}],
        "overdue_titles": [
            {"title": "Launch side project", "days_overdue": 12},
            {"title": "Read 10 books", "days_overdue": 3},
        ],
        "mission": {"title": "Become a published author",
                    "momentum_score": 42, "next_milestone": {"id": 99},
                    "evidence": {"momentum": "moderate", "trend": "stable",
                                 "phase": "Drafting", "momentum_summary": "steady momentum",
                                 "success_drivers": ["2 milestones completed"], "risk_drivers": [],
                                 "recommended_action": "take the next concrete step toward \"Drafting\"",
                                 "as_of": "2026-06-25"}},
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


# Mission losing momentum (EVIDENCE: low/falling), NO overdue/deadline, low
# completion — the evidence-backed mission risk must outrank the portfolio metric.
MISSION_STALLED_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 4,
        "completion_rate": 0.22,
        "overdue_goal_count": 0,
        "active_titles": [{"title": "France 2027 Family 18K Mission",
                           "target_date": None, "is_foundational": True,
                           "evidence": {"momentum": "low", "trend": "falling",
                                        "phase": "Weight-loss foundation phase",
                                        "momentum_summary": "low momentum but slipping",
                                        "success_drivers": [],
                                        "risk_drivers": ["activity has slowed this week"],
                                        "recommended_action": "add one more workout this week to keep the trend moving",
                                        "as_of": "2026-06-25"}}],
        "upcoming_titles": [],
        "overdue_titles": [],
        "mission": {"title": "France 2027 Family 18K Mission",
                    "current_focus": None, "momentum_trend": "falling",
                    "days_remaining": None,
                    "evidence": {"momentum": "low", "trend": "falling",
                                 "phase": "Weight-loss foundation phase",
                                 "momentum_summary": "low momentum but slipping",
                                 "success_drivers": [],
                                 "risk_drivers": ["activity has slowed this week"],
                                 "recommended_action": "add one more workout this week to keep the trend moving",
                                 "as_of": "2026-06-25"}},
    }},
    "habits_state": {"state": {
        "active_habit_count": 2, "avg_completion_rate": 0.6, "longest_streak": 5,
        "streaks_per_habit": [{"name": "Save weekly", "at_risk": False,
                               "current_streak": 5}],
    }},
}

# The France case: steady momentum on strong foundations (weight down, milestone
# achieved, exercise consistency) with a specific, evidence-flagged drag (light
# workout frequency) and a clear phase. Beth must narrate THIS, not portfolio %.
FRANCE_EVIDENCE = {
    "momentum": "moderate", "trend": "stable",
    "phase": "Weight-loss foundation phase",
    "momentum_summary": "steady momentum",
    "success_drivers": ["weight trending down", "milestone achieved",
                        "exercise consistency"],
    "risk_drivers": ["workout frequency is light"],
    "recommended_action": "add one more workout this week to keep the trend moving",
    "as_of": "2026-06-25",
}

# A health goal PROGRESSING via real-world evidence (weight loss, exercise) but with
# ZERO formal habits attached and a lagging milestone %. Healthy momentum MUST
# suppress the "no supporting habits" / "completion low" criticism.
FRANCE_HEALTHY_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 1,
        "completion_rate": 0.22,                 # milestones lag...
        "overdue_goal_count": 0,
        "active_titles": [{"title": "France 2027 Family 18K Mission",
                           "target_date": None, "is_foundational": True,
                           "evidence": FRANCE_EVIDENCE}],
        "upcoming_titles": [],
        "overdue_titles": [],
        "mission": {"title": "France 2027 Family 18K Mission",
                    "current_focus": "Weight-loss foundation phase",
                    "momentum_trend": "stable", "days_remaining": None,
                    "evidence": FRANCE_EVIDENCE},
    }},
    "habits_state": {"state": {
        "active_habit_count": 0, "avg_completion_rate": 0.0, "longest_streak": 0,
        "streaks_per_habit": [],
    }},
}

# No goal-level concern exists at all (no overdue/deadline/mission/at-risk habit,
# habits present) — only here may a portfolio metric become the headline.
PORTFOLIO_ONLY_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 3,
        "completion_rate": 0.20,
        "overdue_goal_count": 0,
        "active_titles": [{"title": "Read more", "target_date": None, "is_foundational": False},
                          {"title": "Learn guitar", "target_date": None, "is_foundational": False}],
        "upcoming_titles": [],
        "overdue_titles": [],
        "mission": None,
    }},
    "habits_state": {"state": {
        "active_habit_count": 2, "avg_completion_rate": 0.55, "longest_streak": 3,
        "streaks_per_habit": [{"name": "Stretch", "at_risk": False}],
    }},
}

_BANNED_GENERIC = ("take one step", "work on the goal", "work on your goals",
                   "make progress today")


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
        self.assertIn("past its target date", ranked[0]["concern"])


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


# ---------------------------------------------------------------------------
# Goal-FIRST refinement — named goals outrank portfolio metrics (Rules 1–5)
# ---------------------------------------------------------------------------
class GoalsGoalFirstTests(SimpleTestCase):
    def _ranked(self, fixture):
        gs = fixture["goals_state"]["state"]
        hs = fixture["habits_state"]["state"]
        return stages._rank_goal_concerns(gs, hs)

    def test_1_named_goal_outranks_portfolio(self):
        top = self._ranked(GOALS_FIXTURE)[0]["concern"]
        self.assertIn("'", top)                                # a named goal
        self.assertNotIn("overall goal completion", top)

    def test_2_mission_risk_outranks_low_completion(self):
        ranked = self._ranked(MISSION_STALLED_FIXTURE)
        self.assertIn("France 2027 Family 18K Mission", ranked[0]["concern"])
        self.assertNotIn("completion", ranked[0]["concern"].lower())
        # the portfolio metric still exists, but lower down (supplemental)
        joined = " ".join(c["concern"].lower() for c in ranked)
        self.assertIn("completion", joined)

    def test_3_focus_today_references_a_real_goal(self):
        a = stages._goals_focus_today_fallback(_wm(GOALS_FIXTURE))
        self.assertIn("Launch side project", a)
        b = stages._goals_focus_today_fallback(_wm(MISSION_STALLED_FIXTURE))
        self.assertIn("France 2027 Family 18K Mission", b)
        # never an abstract portfolio metric as the focus target
        self.assertNotIn("overall goal completion", a.lower())
        self.assertNotIn("overall goal completion", b.lower())

    def test_4_focus_today_ends_with_concrete_action(self):
        for fx in (GOALS_FIXTURE, MISSION_STALLED_FIXTURE):
            out = stages._goals_focus_today_fallback(_wm(fx))
            self.assertIn("one concrete step:", out.lower())

    def test_5_biggest_risk_references_exactly_one_goal(self):
        out = stages._goal_risk_fallback(_wm(GOALS_FIXTURE))
        self.assertNotIn("\n", out)                            # single headline
        self.assertNotIn("1.", out)                            # not a list
        self.assertIn("'", out)                                # a named goal
        self.assertNotIn("overall goal completion", out.lower())

    def test_6_concerns_rank_goal_issues_above_portfolio(self):
        out = stages._goal_concerns_fallback(_wm(GOALS_FIXTURE))
        first_line = out.splitlines()[1]                       # "1. ..."
        self.assertTrue(first_line.startswith("1."))
        self.assertIn("'", first_line)                         # named goal first
        self.assertNotIn("overall goal completion", first_line.lower())

    def test_7_portfolio_headline_only_when_no_goal_concern(self):
        # portfolio-only fixture: the headline MAY be a portfolio metric
        top_portfolio = self._ranked(PORTFOLIO_ONLY_FIXTURE)[0]["concern"]
        self.assertIn("overall goal completion", top_portfolio.lower())
        # but whenever a goal-level concern exists, it is NEVER the headline
        for fx in (GOALS_FIXTURE, MISSION_STALLED_FIXTURE):
            self.assertNotIn("overall goal completion",
                             self._ranked(fx)[0]["concern"].lower())

    def test_8_no_fabricated_stall_detection(self):
        # Non-mission goals with no canonical risk signal must NOT be called
        # stalled / slipping / losing momentum.
        ranked = self._ranked(PORTFOLIO_ONLY_FIXTURE)
        blob = " ".join(c["concern"].lower() for c in ranked)
        for word in ("stalled", "slipping", "losing momentum", "stalling"):
            self.assertNotIn(word, blob)
        for name in ("read more", "learn guitar"):
            self.assertNotIn(name, blob)                       # never named as at-risk

    def test_9_no_generic_take_one_step_language(self):
        outs = []
        for fx in (GOALS_FIXTURE, MISSION_STALLED_FIXTURE, PORTFOLIO_ONLY_FIXTURE):
            wm = _wm(fx)
            outs += [stages._goal_risk_fallback(wm),
                     stages._goals_focus_today_fallback(wm),
                     stages._goal_concerns_fallback(wm)]
        blob = " ".join(outs).lower()
        for phrase in _BANNED_GENERIC:
            self.assertNotIn(phrase, blob, f"generic coaching leaked: {phrase}")

    def test_10_health_ranking_untouched(self):
        # Health reasoning functions are not modified by the goals refinement.
        self.assertTrue(hasattr(stages, "_rank_health_concerns"))
        self.assertIsNot(stages._rank_health_concerns, stages._rank_goal_concerns)
        # health deterministic routing unchanged (byte-identical contract)
        self.assertEqual(planmod.deterministic_intent("what is my biggest health risk"),
                         "biggest_health_risk")


# ---------------------------------------------------------------------------
# Evidence-FIRST refinement — Beth narrates the momentum engine, not metadata
# ---------------------------------------------------------------------------
class GoalsEvidenceFirstTests(SimpleTestCase):
    _GENERIC = ("focus on fewer goals", "improve completion rate",
                "overall goal completion", "take one step", "make progress today",
                "no supporting habits")

    def _ranked(self, fixture):
        gs = fixture["goals_state"]["state"]
        hs = fixture["habits_state"]["state"]
        return stages._rank_goal_concerns(gs, hs)

    def test_healthy_momentum_suppresses_missing_habit_and_portfolio(self):
        # France progressing (steady, ZERO habits, lagging milestone %): never
        # criticised for missing habits or completion %, despite hactive==0.
        blob = " ".join(c["concern"].lower() for c in self._ranked(FRANCE_HEALTHY_FIXTURE))
        self.assertNotIn("no supporting habits", blob)
        self.assertNotIn("isn't backed by a routine", blob)
        self.assertNotIn("overall goal completion", blob)

    def test_biggest_risk_is_evidence_driver_not_metadata(self):
        # The France headline is the engine's specific drag, naming the goal.
        risk = stages._goal_risk_fallback(_wm(FRANCE_HEALTHY_FIXTURE))
        self.assertIn("France 2027 Family 18K Mission", risk)
        self.assertIn("workout frequency is light", risk)
        for g in self._GENERIC:
            self.assertNotIn(g, risk.lower())

    def test_focus_today_uses_recommended_action(self):
        out = stages._goals_focus_today_fallback(_wm(FRANCE_HEALTHY_FIXTURE))
        self.assertIn("France 2027 Family 18K Mission", out)
        self.assertIn("add one more workout this week", out)   # the driver action
        for g in self._GENERIC:
            self.assertNotIn(g, out.lower())

    def test_phase_success_and_risk_drivers_exposed(self):
        ev = (stages.goals_working_memory(FRANCE_HEALTHY_FIXTURE)
              .get("goal_evidence") or [])
        self.assertTrue(ev)
        item = ev[0]
        self.assertEqual(item["phase"], "Weight-loss foundation phase")
        self.assertIn("weight trending down", item.get("whats_working", []))
        self.assertIn("workout frequency is light", item.get("watch", []))
        self.assertIn("add one more workout this week", item.get("recommended_action", ""))

    def test_evidence_backed_stall_outranks_metadata(self):
        ranked = self._ranked(MISSION_STALLED_FIXTURE)
        self.assertIn("France 2027 Family 18K Mission", ranked[0]["concern"])
        self.assertIn("momentum", ranked[0]["concern"].lower())
        self.assertNotIn("completion", ranked[0]["concern"].lower())

    def test_progress_narrates_phase_and_drivers(self):
        out = stages._goals_progress_fallback(_wm(FRANCE_HEALTHY_FIXTURE))
        self.assertIn("France 2027 Family 18K Mission", out)
        self.assertIn("Weight-loss foundation phase", out)     # phase
        self.assertIn("weight trending down", out)             # success driver
        self.assertIn("steady momentum", out)                  # momentum summary

    def test_no_generic_coaching_when_evidence_exists(self):
        outs = []
        wm = _wm(FRANCE_HEALTHY_FIXTURE)
        outs += [stages._goal_risk_fallback(wm),
                 stages._goals_focus_today_fallback(wm),
                 stages._goals_progress_fallback(wm),
                 stages._goal_concerns_fallback(wm)]
        blob = " ".join(outs).lower()
        for g in self._GENERIC:
            self.assertNotIn(g, blob, f"generic coaching leaked with evidence: {g}")

    def test_no_raw_momentum_json_or_scores_leak(self):
        for fx in (GOALS_FIXTURE, MISSION_STALLED_FIXTURE, FRANCE_HEALTHY_FIXTURE):
            blob = json.dumps(stages.goals_working_memory(fx))
            for forbidden in ("momentum_score", "progress_score", "snapshot",
                              "\"rising\"", "\"falling\"", "\"stable\"", "\"moderate\"",
                              "as_of", "signal_scores", "success_drivers", "risk_drivers"):
                self.assertNotIn(forbidden, blob, f"leaked: {forbidden}")

    def test_fallbacks_always_answer_with_evidence_fixtures(self):
        for fx in (FRANCE_HEALTHY_FIXTURE, MISSION_STALLED_FIXTURE):
            wm = _wm(fx)
            for fb in (stages._goal_risk_fallback, stages._goals_progress_fallback,
                       stages._goal_concerns_fallback, stages._goals_focus_today_fallback):
                out = fb(wm)
                self.assertTrue(out and len(out) > 20)


# ---------------------------------------------------------------------------
# build_goal_state — exposes snapshot evidence, READ-ONLY (no recompute), no N+1
# ---------------------------------------------------------------------------
class BuildGoalStateEvidenceTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeDomain, LifeGoal, GoalMilestone
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        from apps.core.time.system_clock import get_current_time

        self.user = User.objects.create_user(email="goalsev@example.com",
                                              password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=dj_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        domain = LifeDomain.objects.create(name="Health", slug="health")
        today = get_current_time().date()
        # The rich goal: success (domain signals) + risk (habits) drivers + phase.
        self.rich = LifeGoal.objects.create(
            user=self.user, title="France 2027", domain=domain, status="active",
            target_date=today + timedelta(days=300))
        GoalMilestone.objects.create(goal=self.rich, title="Build base",
                                     completed=False)
        GoalMomentumSnapshot.objects.create(
            user=self.user, goal=self.rich, snapshot_date=today,
            momentum_score=80, progress_score=40, momentum_trend="rising",
            drivers={
                "domain_signals": {"score": 80, "label": "Weight trend: down",
                                   "signal_labels": ["weight trending down",
                                                     "3 workouts this week"]},
                "habits": {"score": 20, "label": "Start a habit to build momentum"},
            })
        # Two more (with snapshots) so the N+1 test has multiple goals.
        for i in range(2):
            g = LifeGoal.objects.create(user=self.user, title=f"Goal {i}",
                                        domain=domain, status="active",
                                        target_date=today + timedelta(days=400 + i))
            GoalMomentumSnapshot.objects.create(
                user=self.user, goal=g, snapshot_date=today,
                momentum_score=55, progress_score=30, momentum_trend="stable",
                drivers={"habits": {"score": 50, "label": "Habits: getting started"}})

    def _france_entry(self, state):
        for t in (state.get("active_titles") or []):
            if t.get("title") == "France 2027":
                return t
        return None

    def test_evidence_exposed_banded_and_sanitized(self):
        from apps.core.ai_state.state_builder import build_goal_state
        state = build_goal_state(self.user)
        entry = self._france_entry(state)
        self.assertIsNotNone(entry)
        ev = entry.get("evidence")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["momentum"], "strong")       # 80 -> banded
        self.assertEqual(ev["trend"], "rising")
        self.assertNotIn("momentum_score", ev)           # no raw 0-100 score

    def test_narrative_phase_success_risk_and_recommendation(self):
        from apps.core.ai_state.state_builder import build_goal_state
        ev = self._france_entry(build_goal_state(self.user)).get("evidence")
        self.assertEqual(ev["phase"], "Build base")                       # milestone
        self.assertIn("weight trending down", ev["success_drivers"])      # high-score
        self.assertIn("Start a habit to build momentum", ev["risk_drivers"])  # low-score
        self.assertTrue(ev["recommended_action"])
        # recommendation is tied to the risk driver (habit), not generic
        self.assertIn("habit", ev["recommended_action"].lower())

    def test_no_recompute_on_request_path(self):
        # build_goal_state must READ the nightly snapshot, never recompute it.
        from apps.core.ai_state.state_builder import build_goal_state
        import apps.dashboard_v2.services.momentum_service as ms

        def _boom(*a, **k):
            raise AssertionError("momentum recomputed on the request path")

        patches = []
        for attr in ("compute_and_persist", "compute_momentum"):
            if hasattr(ms.GoalMomentumService, attr):
                patches.append(patch.object(ms.GoalMomentumService, attr, _boom))
        for p in patches:
            p.start()
        try:
            state = build_goal_state(self.user)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(state.get("active_titles"))

    def test_snapshot_query_is_bounded_no_n_plus_1(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        from apps.core.ai_state.state_builder import build_goal_state
        with CaptureQueriesContext(connection) as ctx:
            build_goal_state(self.user)
        snap_queries = [q for q in ctx.captured_queries
                        if "momentumsnapshot" in q["sql"].lower()]
        # 3 goals -> at most 2 snapshot reads (the bulk active-goal query + the
        # mission's own latest), never one-per-goal.
        self.assertLessEqual(len(snap_queries), 2, snap_queries)


# ---------------------------------------------------------------------------
# Named-goal PRE-ROUTER — root cause #1: a question about a named goal/mission
# must be OWNED by the Goals domain, never stolen by the health planner. Pure
# decision logic (no DB) + the canonical-state wrapper.
# ---------------------------------------------------------------------------
class NamedGoalPrerouteDecisionTests(SimpleTestCase):
    TITLES = ["France 2027", "Write a book"]
    MISSION = "Become a published author"

    def _route(self, msg, titles=None, mission=None):
        titles = self.TITLES if titles is None else titles
        mission = self.MISSION if mission is None else mission
        return planmod.named_goal_intent(msg, titles, mission)[0]   # (intent, matched)

    def test_named_goal_progress_routes_to_goals(self):
        # (1) named-goal progress questions route to Goals, not Health.
        for msg in ("how is France 2027 progressing",
                    "how's France 2027 going",
                    "where am i on Write a book",
                    "give me an update on France 2027"):
            self.assertEqual(self._route(msg), "goals_progress", msg)

    def test_mission_and_deictic_route_to_goals(self):
        # (2) "my mission" and "this goal" route to Goals.
        for msg in ("how is my mission going",
                    "tell me about this goal",
                    "what's the status of that goal",
                    "how is Become a published author tracking"):
            self.assertIsNotNone(self._route(msg), msg)

    def test_named_goal_risk_and_focus_intents(self):
        self.assertEqual(self._route("what's my biggest risk on France 2027"),
                         "biggest_goal_risk")
        self.assertEqual(self._route("what should i do today for France 2027"),
                         "goals_focus_today")

    def test_focus_on_for_this_goal_routes_to_focus_today(self):
        # Defect C: "focus on" / "focus for" with a goal reference -> focus_today.
        self.assertEqual(self._route("what should i focus on for this goal"),
                         "goals_focus_today")
        self.assertEqual(self._route("what should i focus on for France 2027"),
                         "goals_focus_today")
        self.assertEqual(self._route("what to focus on for this mission"),
                         "goals_focus_today")

    def test_health_questions_never_routed_to_goals(self):
        # (3) Health questions still route to Health (pre-router returns None,
        # leaving the existing health path untouched). Includes the "goal weight"
        # trap — a health question that merely contains the word "goal".
        for msg in ("what is my biggest health risk",
                    "what are my health concerns",
                    "what should i focus on today",
                    "how am i doing",
                    "what's my goal weight"):
            self.assertIsNone(self._route(msg), msg)

    def test_rhythm_and_general_questions_unchanged(self):
        # (4) rhythm / general questions remain unchanged (None -> planner path).
        for msg in ("what should i do next", "who was abraham lincoln",
                    "thanks", "remind me to call mom"):
            self.assertIsNone(self._route(msg), msg)

    def test_deictic_routes_without_titles(self):
        # Defect A fix: an unambiguous goal deictic routes to Goals even when NO
        # titles are loaded (cold/empty snapshot). This is the Q2 ("how is my
        # mission going") fix — it must NOT depend on titles existing.
        self.assertEqual(self._route("how is my mission going", titles=[], mission=None),
                         "goals_progress")
        self.assertEqual(self._route("what should i focus on for this goal",
                                     titles=[], mission=None), "goals_focus_today")
        # A NAMED title with no titles loaded still can't match (needs the title) —
        # the DB fallback (wrapper) covers that case.
        self.assertIsNone(self._route("how is France 2027 going", titles=[], mission=None))

    def test_title_gates_prevent_stealing(self):
        # A goal literally named "Health" must NOT steal the health question
        # (bare domain-collision word); short titles are length-gated out.
        self.assertIsNone(self._route("what is my biggest health risk",
                                      titles=["Health"], mission=None))
        self.assertIsNone(self._route("how is it going", titles=["ab"], mission=None))


class NamedGoalPrerouteWrapperTests(TestCase):
    """preroute_named_goal reads canonical goals_state (read-only) and applies the
    decision against REAL state shape produced by build_goal_state."""

    def setUp(self):
        from datetime import timedelta
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeDomain, LifeGoal, GoalMilestone
        from apps.core.time.system_clock import get_current_time

        self.user = User.objects.create_user(email="preroute@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=dj_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        domain = LifeDomain.objects.create(name="Purpose", slug="purpose")
        today = get_current_time().date()
        g = LifeGoal.objects.create(user=self.user, title="France 2027",
                                    domain=domain, status="active",
                                    target_date=today + timedelta(days=300))
        GoalMilestone.objects.create(goal=g, title="Build aerobic base", completed=False)

    @patch("apps.ai.cos_services.get_domain_state")
    def test_wrapper_routes_named_goal_with_populated_snapshot(self, mock_gds):
        from apps.core.ai_state.state_builder import build_goal_state
        mock_gds.return_value = {"status": "ready", "state": build_goal_state(self.user)}
        self.assertEqual(
            planmod.preroute_named_goal(self.user, "how is France 2027 progressing"),
            "goals_progress")
        self.assertIsNone(
            planmod.preroute_named_goal(self.user, "what is my biggest health risk"))
        self.assertTrue(mock_gds.called)

    @patch("apps.ai.cos_services.get_domain_state",
           return_value={"status": "pending", "state": None})
    def test_wrapper_db_fallback_on_empty_snapshot(self, _mock):
        # Root cause: cold/pending snapshot -> no titles. The DB fallback must
        # recover the named goal, and the deictic must route with no titles.
        self.assertEqual(
            planmod.preroute_named_goal(self.user, "how is France 2027 going"),
            "goals_progress")                                   # DB title fallback
        self.assertEqual(
            planmod.preroute_named_goal(self.user, "how is my mission going"),
            "goals_progress")                                   # deictic, no titles
        self.assertEqual(
            planmod.preroute_named_goal(self.user, "what should i focus on for this goal"),
            "goals_focus_today")
        self.assertIsNone(
            planmod.preroute_named_goal(self.user, "what is my biggest health risk"))

    @patch("apps.ai.cos_services.get_domain_state", side_effect=RuntimeError("boom"))
    def test_wrapper_db_fallback_on_read_failure(self, _mock):
        # Snapshot read throws -> degrade to the DB title fallback, still route.
        self.assertEqual(
            planmod.preroute_named_goal(self.user, "how is France 2027 going"),
            "goals_progress")

    @patch("apps.ai.cos_services.get_domain_state",
           return_value={"status": "pending", "state": None})
    def test_wrapper_no_goals_named_title_returns_none(self, _mock):
        from apps.purpose.models import LifeGoal
        LifeGoal.objects.filter(user=self.user).delete()        # no active goals at all
        self.assertIsNone(
            planmod.preroute_named_goal(self.user, "how is France 2027 going"))


# ---------------------------------------------------------------------------
# Rich goal context (Fix #2) + milestone-grounded recommendation (Fix #3) —
# root cause #2: goals reasoning no longer ignores canonical goal context.
# ---------------------------------------------------------------------------
class RichGoalContextTests(TestCase):
    def setUp(self):
        from datetime import timedelta
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeDomain, LifeGoal, GoalMilestone
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        from apps.core.time.system_clock import get_current_time

        self.user = User.objects.create_user(email="richctx@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=dj_settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        domain = LifeDomain.objects.create(name="Purpose", slug="purpose")
        today = get_current_time().date()
        self.goal = LifeGoal.objects.create(
            user=self.user, title="France 2027", domain=domain, status="active",
            target_date=today + timedelta(days=300),
            why_it_matters="To run the family 18K with my kids in France.",
            success_looks_like="Finish the 18K route under 2 hours, together.")
        # A completed milestone (the recent win) + the active milestone (with a
        # description) + a future milestone — ordered by target_date.
        GoalMilestone.objects.create(
            goal=self.goal, title="Buy running shoes", completed=True,
            completed_date=today - timedelta(days=5),
            target_date=today - timedelta(days=7))
        GoalMilestone.objects.create(
            goal=self.goal, title="Build aerobic base", completed=False,
            description="Three easy zone-2 runs per week for a month.",
            target_date=today + timedelta(days=10))
        GoalMilestone.objects.create(
            goal=self.goal, title="Run a 5K", completed=False,
            target_date=today + timedelta(days=40))
        # Snapshot with HIGH-score drivers only -> no risk driver -> the rec must
        # fall through to the active-milestone anchor (Fix #3).
        GoalMomentumSnapshot.objects.create(
            user=self.user, goal=self.goal, snapshot_date=today,
            momentum_score=80, progress_score=45, momentum_trend="rising",
            drivers={"domain_signals": {"score": 80, "label": "Training on track",
                                        "signal_labels": ["3 runs this week"]}})

    def _france(self, state):
        for t in (state.get("active_titles") or []):
            if t.get("title") == "France 2027":
                return t
        return None

    def _state(self):
        from apps.core.ai_state.state_builder import build_goal_state
        return build_goal_state(self.user)

    def test_build_goal_state_exposes_rich_context(self):
        # (5) build_goal_state exposes rich milestone/context fields.
        ctx = self._france(self._state()).get("context")
        self.assertIsNotNone(ctx)
        self.assertTrue(ctx["has_milestones"])
        self.assertEqual(ctx["current_phase"], "Build aerobic base")
        self.assertEqual(ctx["active_milestone"], "Build aerobic base")
        self.assertIn("zone-2", ctx["active_milestone_detail"].lower())
        self.assertIn("Run a 5K", ctx["next_milestones"])
        self.assertEqual(ctx["recently_completed_milestone"], "Buy running shoes")
        self.assertIn("family", ctx["why_it_matters"].lower())
        self.assertIn("finish", ctx["success_definition"].lower())

    def test_recommendation_grounded_in_active_milestone(self):
        # (7) recommendations use active milestone / phase context, and
        # (6) richly planned goals do not receive generic planning advice.
        ev = self._france(self._state()).get("evidence")
        self.assertIsNotNone(ev)
        rec = ev["recommended_action"]
        self.assertIn("Build aerobic base", rec)
        for g in ("take one step", "make progress", "plan the goal",
                  "outline next steps", "work on the goal"):
            self.assertNotIn(g, rec.lower())

    def test_curator_surfaces_context_to_reasoning(self):
        truth = {"goals_state": {"state": self._state()},
                 "habits_state": {"state": {}}}
        ev = (stages.goals_working_memory(truth).get("goal_evidence") or [])
        france = next((i for i in ev if i.get("goal") == "France 2027"), None)
        self.assertIsNotNone(france)
        self.assertEqual(france.get("phase"), "Build aerobic base")
        self.assertIn("zone-2", france.get("current_milestone_detail", "").lower())
        self.assertIn("why_it_matters", france)
        self.assertIn("success_looks_like", france)
        self.assertEqual(france.get("recently_completed"), "Buy running shoes")

    def test_focus_today_fallback_is_milestone_grounded(self):
        # (6/7) the user-facing fallback names the milestone, never generic.
        truth = {"goals_state": {"state": self._state()},
                 "habits_state": {"state": {}}}
        wm = {"intent": "goals_focus_today",
              "facts": stages.goals_working_memory(truth)}
        out = stages._goals_focus_today_fallback(wm).lower()
        self.assertIn("build aerobic base", out)
        for g in _BANNED_GENERIC:
            self.assertNotIn(g, out, g)

    def test_no_raw_ids_enums_or_source_paths_leak(self):
        # (8) no raw IDs, enums, source paths, or internal JSON leaks.
        truth = {"goals_state": {"state": self._state()},
                 "habits_state": {"state": {}}}
        blob = json.dumps(stages.goals_working_memory(truth))
        for forbidden in ("momentum_score", "progress_score", "is_foundational",
                          "SAE.", "success_drivers", "risk_drivers", "as_of",
                          "signal_labels", "_id\""):
            self.assertNotIn(forbidden, blob, f"leaked: {forbidden}")
