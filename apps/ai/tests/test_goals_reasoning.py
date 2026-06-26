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
                          "drivers": ["weight trending down"], "as_of": "2026-06-25"}},
            {"title": "Write a book", "target_date": "2026-12-01", "is_foundational": False,
             "evidence": {"momentum": "moderate", "trend": "stable",
                          "drivers": ["2 milestones completed"], "as_of": "2026-06-25"}},
        ],
        "upcoming_titles": [{"title": "Finish chapter 3", "days_remaining": 4}],
        "overdue_titles": [
            {"title": "Launch side project", "days_overdue": 12},
            {"title": "Read 10 books", "days_overdue": 3},
        ],
        "mission": {"title": "Become a published author",
                    "momentum_score": 42, "next_milestone": {"id": 99},
                    "evidence": {"momentum": "moderate", "trend": "stable",
                                 "drivers": ["2 milestones completed"],
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
                                        "drivers": ["activity has slowed this week"],
                                        "as_of": "2026-06-25"}}],
        "upcoming_titles": [],
        "overdue_titles": [],
        "mission": {"title": "France 2027 Family 18K Mission",
                    "current_focus": None, "momentum_trend": "falling",
                    "days_remaining": None,
                    "evidence": {"momentum": "low", "trend": "falling",
                                 "drivers": ["activity has slowed this week"],
                                 "as_of": "2026-06-25"}},
    }},
    "habits_state": {"state": {
        "active_habit_count": 2, "avg_completion_rate": 0.6, "longest_streak": 5,
        "streaks_per_habit": [{"name": "Save weekly", "at_risk": False,
                               "current_streak": 5}],
    }},
}

# The France case: a health goal PROGRESSING via real-world evidence (weight loss,
# exercise) but with ZERO formal habits attached and a lagging milestone %. Healthy
# momentum MUST suppress the "no supporting habits" / "completion low" criticism.
FRANCE_HEALTHY_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 1,
        "completion_rate": 0.22,                 # milestones lag...
        "overdue_goal_count": 0,
        "active_titles": [{"title": "France 2027 Family 18K Mission",
                           "target_date": None, "is_foundational": True,
                           "evidence": {"momentum": "strong", "trend": "rising",
                                        "drivers": ["weight trending down",
                                                    "4 workouts this week"],
                                        "as_of": "2026-06-25"}}],
        "upcoming_titles": [],
        "overdue_titles": [],
        "mission": {"title": "France 2027 Family 18K Mission",
                    "current_focus": None, "momentum_trend": "rising",
                    "days_remaining": None,
                    "evidence": {"momentum": "strong", "trend": "rising",
                                 "drivers": ["weight trending down",
                                             "4 workouts this week"],
                                 "as_of": "2026-06-25"}},
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
    def _ranked(self, fixture):
        gs = fixture["goals_state"]["state"]
        hs = fixture["habits_state"]["state"]
        return stages._rank_goal_concerns(gs, hs)

    def test_healthy_momentum_suppresses_missing_habit(self):
        # France progressing (strong/rising) with ZERO habits -> never criticised
        # for missing habits, and not flagged for lagging milestone %.
        ranked = self._ranked(FRANCE_HEALTHY_FIXTURE)
        blob = " ".join(c["concern"].lower() for c in ranked)
        self.assertNotIn("no supporting habits", blob)
        self.assertNotIn("isn't backed by a routine", blob)
        self.assertNotIn("overall goal completion", blob)
        # with the only goal progressing, biggest risk says on-track, not criticism
        risk = stages._goal_risk_fallback(_wm(FRANCE_HEALTHY_FIXTURE)).lower()
        self.assertIn("on track", risk)

    def test_evidence_backed_risk_outranks_metadata(self):
        ranked = self._ranked(MISSION_STALLED_FIXTURE)
        self.assertIn("France 2027 Family 18K Mission", ranked[0]["concern"])
        self.assertIn("momentum", ranked[0]["concern"].lower())
        self.assertNotIn("completion", ranked[0]["concern"].lower())

    def test_progress_narrates_evidence(self):
        out = stages._goals_progress_fallback(_wm(FRANCE_HEALTHY_FIXTURE))
        self.assertIn("France 2027 Family 18K Mission", out)
        self.assertIn("momentum", out.lower())
        # driver evidence surfaces in coaching language
        self.assertIn("weight trending down", out)

    def test_no_raw_momentum_json_or_scores_leak(self):
        # Curated output must never carry raw scores, trend enums, or JSON keys.
        for fx in (GOALS_FIXTURE, MISSION_STALLED_FIXTURE, FRANCE_HEALTHY_FIXTURE):
            blob = json.dumps(stages.goals_working_memory(fx))
            for forbidden in ("momentum_score", "progress_score", "snapshot",
                              "\"rising\"", "\"falling\"", "\"stable\"",
                              "as_of", "signal_scores"):
                self.assertNotIn(forbidden, blob, f"leaked: {forbidden}")

    def test_evidence_curated_as_coaching_language(self):
        facts = stages.goals_working_memory(FRANCE_HEALTHY_FIXTURE)
        ev = facts.get("goal_evidence") or []
        self.assertTrue(ev)
        self.assertEqual(ev[0]["goal"], "France 2027 Family 18K Mission")
        self.assertIn("momentum", ev[0]["status"])         # banded coaching word
        self.assertIn("trending up", ev[0]["status"])       # translated, not "rising"

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
        from django.conf import settings as dj_settings
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeDomain, LifeGoal
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
        for i in range(3):
            g = LifeGoal.objects.create(user=self.user, title=f"Goal {i}",
                                        domain=domain, status="active")
            GoalMomentumSnapshot.objects.create(
                user=self.user, goal=g, snapshot_date=today,
                momentum_score=80, progress_score=40, momentum_trend="rising",
                drivers={"habits": {"score": 28, "label": "4/5 habits completed"}})

    def test_evidence_exposed_banded_and_sanitized(self):
        from apps.core.ai_state.state_builder import build_goal_state
        state = build_goal_state(self.user)
        titles = state.get("active_titles") or []
        self.assertTrue(titles)
        ev = titles[0].get("evidence")
        self.assertIsNotNone(ev)
        self.assertEqual(ev["momentum"], "strong")       # 80 -> banded
        self.assertEqual(ev["trend"], "rising")
        self.assertIn("4/5 habits completed", ev["drivers"])
        # banded — no raw 0-100 score on the entry
        self.assertNotIn("momentum_score", ev)

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
