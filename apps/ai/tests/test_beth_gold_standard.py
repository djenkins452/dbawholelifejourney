# ==============================================================================
# File: apps/ai/tests/test_beth_gold_standard.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: BETH GOLD-STANDARD ACCEPTANCE — quality gates beyond routing.
#   Every high-frequency answer must clear five gates: EVIDENCE, SYNTHESIS,
#   ACTIONABLE, NON-TEMPLATED, DISTINCT. A response that sounds templated, repeats
#   generic coaching, lacks synthesis/evidence/actionable guidance, or is
#   indistinguishable from another intent FAILS. Spec: docs/BETH_GOLD_STANDARD_ACCEPTANCE.md
# ==============================================================================
import re
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import stages

MISSION = "France 2027 Family 18K Mission"

# ---- quality-gate primitives ----------------------------------------------
_BANNED = tuple(stages._BANNED_FOCUS) + (
    "do your best", "stay focused", "you've got this", "keep it up",
    "you're doing fine", "doing great", "you got this", "just keep going",
)
_MOMENTUM = ("momentum", "trending", "thriving", "steady", "stalled", "drifting",
             "strong", "rising", "falling", "on pace", "high", "low", "short")
_EVIDENCE = _MOMENTUM + ("phase", "milestone", "workout", "weight", "glucose",
                         "sleep", "protein", "nutrition", "habit", "blood sugar")
_ACTION = ("complete", "log ", "walk", "write", "read ", "journal", "schedule",
           "define", "reschedule", "protein", "workout", "bedtime", "wind down",
           "prepare for tomorrow", "spend ", "milestone", "hit your", "block ",
           "reach out", "15", "20", "30", "lever")


def _has_evidence(a):
    al = a.lower()
    return bool(re.search(r"\d", a)) or any(w in al for w in _EVIDENCE)


def _is_actionable(a):
    al = a.lower()
    return any(c in al for c in _ACTION)


def _banned_hits(a):
    al = a.lower()
    return [b for b in _BANNED if b in al]


def _synthesis_dims(a):
    al = a.lower()
    groups = (
        ("momentum", "trending", "steady", "strong", "stalled", "drifting", "thriving"),
        ("phase", "milestone"),
        ("workout", "weight", "protein", "glucose", "sleep", "nutrition", "habit", "blood sugar"),
        ("risk", "watch", "slip", "light", "drop", "fail", "strength"),
        ("next", "today", "tomorrow", "step", "move", "lever"),
        # meaning/values dimension — for rationale answers (why a goal matters)
        ("family", "health", "values", "finish", "kids", "decades", "matters", "means"),
    )
    return sum(1 for g in groups if any(w in al for w in g))


# ---- fixtures (rich France mission + a health profile) ---------------------
_CTX = {
    "has_milestones": True, "current_phase": "weight-loss foundation phase",
    "active_milestone": "weight-loss foundation phase",
    "active_milestone_detail": "reach 284.9 lb — protein, hydration, scheduled workouts",
    "next_milestones": ["a return to running base"],
    "recently_completed_milestone": "bought running shoes",
    "why_it_matters": "To run the 18K in France with my family and stay healthy enough "
                      "to keep up with my kids for decades.",
    "success_definition": "Crossing the France 18K finish line together as a family in 2027.",
}
_EV = {
    "state": "stable", "momentum": "moderate", "trend": "stable",
    "phase": "weight-loss foundation phase", "momentum_summary": "steady momentum",
    "success_drivers": ["weight trending down", "workouts on schedule"],
    "risk_drivers": ["workout frequency is light"],
    "recommended_action": "complete today's scheduled workout and hit your protein target",
}
FRANCE = {
    "goals_state": {"state": {
        "active_goal_count": 3, "completion_rate": 0.4, "overdue_goal_count": 0,
        "active_titles": [{"title": MISSION, "target_date": None, "context": _CTX,
                           "evidence": _EV}],
        "upcoming_titles": [], "overdue_titles": [],
        "mission": {"title": MISSION, "context": _CTX, "evidence": _EV},
    }},
    "habits_state": {"state": {"active_habit_count": 1, "avg_completion_rate": 0.6,
                               "streaks_per_habit": []}},
}


def _gwm(intent):
    return {"intent": intent, "facts": stages.goals_working_memory(FRANCE)}


HEALTH_WM = {"facts": {
    "current_status": {"weight_current": 248, "weight_unit": "lb",
                       "latest_glucose": 165, "latest_glucose_unit": "mg/dL",
                       "sleep_avg_hours_7d": 6.2},
    "trends": {"weight_trend": "trending down"},
    "goal_progress": {"weight_goal_remaining": 8},
    "nutrition_context": {"day_phase": "afternoon"},
    "ranked_concerns": [
        {"concern": "your blood sugar has been running high lately",
         "action": "a short walk after meals and steadier carb timing is the highest-leverage move"},
        {"concern": "you've been averaging under 6.5 hours of sleep, which makes everything harder",
         "action": "protecting a consistent bedtime this week is the best next step"},
    ],
}}


class GoldStandardMixin:
    def assert_gold(self, answer, *, required=(), forbidden=(), action=True,
                    min_synthesis=2):
        self.assertTrue(answer and len(answer) > 40, f"too short: {answer!r}")
        self.assertTrue(_has_evidence(answer), f"GATE evidence failed: {answer!r}")
        self.assertEqual(_banned_hits(answer), [],
                         f"GATE non-templated failed: {_banned_hits(answer)} in {answer!r}")
        self.assertGreaterEqual(_synthesis_dims(answer), min_synthesis,
                                f"GATE synthesis failed ({_synthesis_dims(answer)} dims): {answer!r}")
        if action:
            self.assertTrue(_is_actionable(answer), f"GATE actionable failed: {answer!r}")
        for r in required:
            self.assertIn(r.lower(), answer.lower(), f"missing required '{r}': {answer!r}")
        for fbd in forbidden:
            self.assertNotIn(fbd.lower(), answer.lower(), f"forbidden '{fbd}': {answer!r}")


# ===========================================================================
# GOALS — six gold answers
# ===========================================================================
class GoalsGoldStandard(SimpleTestCase, GoldStandardMixin):
    def test_progress(self):
        a = stages._goals_progress_fallback(_gwm("goals_progress"))
        self.assert_gold(a, required=(MISSION, "phase"),
                         forbidden=("you have 3 active",))

    def test_on_track(self):
        a = stages._goal_on_track_fallback(_gwm("goal_on_track"))
        self.assert_gold(a, required=(MISSION, "next move"))
        self.assertTrue(a.lower().startswith("yes") or "on track" in a.lower())

    def test_why_priority(self):
        a = stages._goal_why_priority_fallback(_gwm("goal_why_priority"))
        # rationale, not action — meaning/values required, metadata forbidden
        self.assert_gold(a, required=("family",), action=False, min_synthesis=1,
                         forbidden=("active goal", "deadline", "completion", "momentum score"))

    def test_next_milestone(self):
        a = stages._goal_next_milestone_fallback(_gwm("goal_next_milestone"))
        self.assert_gold(a, required=("milestone", "running base"), action=False)

    def test_failure_modes(self):
        a = stages._goal_failure_modes_fallback(_gwm("goal_failure_modes"))
        self.assert_gold(a, required=("fail",))
        self.assertTrue(any(k in a.lower() for k in ("workout", "nutrition", "routine")))

    def test_focus_today(self):
        a = stages._goals_focus_today_fallback(_gwm("goals_focus_today"))
        self.assert_gold(a, required=("today",))

    def test_confidence(self):
        a = stages._goal_confidence_fallback(_gwm("goal_confidence"))
        self.assert_gold(a, required=("confiden",))
        self.assertTrue(any(k in a.lower() for k in ("high", "solid", "moderate", "low")))

    def test_six_goal_intents_pairwise_distinct(self):
        answers = [
            stages._goals_progress_fallback(_gwm("goals_progress")),
            stages._goal_on_track_fallback(_gwm("goal_on_track")),
            stages._goal_why_priority_fallback(_gwm("goal_why_priority")),
            stages._goal_next_milestone_fallback(_gwm("goal_next_milestone")),
            stages._goal_failure_modes_fallback(_gwm("goal_failure_modes")),
            stages._goal_confidence_fallback(_gwm("goal_confidence")),
        ]
        self.assertEqual(len(set(answers)), 6, "goal intents collapsed")
        # distinct openings too (not just trailing text)
        self.assertEqual(len({a.split('.')[0].lower() for a in answers}), 6)


# ===========================================================================
# HEALTH — four gold answers
# ===========================================================================
class HealthGoldStandard(SimpleTestCase, GoldStandardMixin):
    def test_biggest_risk(self):
        a = stages._health_risk_fallback(HEALTH_WM)
        self.assert_gold(a, required=("blood sugar",))
        self.assertNotIn("\n", a)                       # single headline, not a list

    def test_overall_progress(self):
        a = stages._health_progress_fallback(HEALTH_WM)
        # a multi-metric summary; action optional (the focus intent owns the step)
        self.assert_gold(a, action=False, min_synthesis=2)
        self.assertTrue(sum(m in a.lower() for m in ("weight", "glucose", "sleep")) >= 2)

    def test_focus_today(self):
        a = stages._health_focus_today_fallback(HEALTH_WM)
        self.assert_gold(a, required=("today",))

    def test_concerns_is_a_list(self):
        a = stages._health_concerns_fallback(HEALTH_WM)
        self.assert_gold(a, action=False)
        self.assertIn("2.", a)                          # ranked list, ≥2

    def test_health_intents_distinct(self):
        answers = [
            stages._health_risk_fallback(HEALTH_WM),
            stages._health_progress_fallback(HEALTH_WM),
            stages._health_focus_today_fallback(HEALTH_WM),
            stages._health_concerns_fallback(HEALTH_WM),
        ]
        self.assertEqual(len(set(answers)), 4, "health intents collapsed")


# ===========================================================================
# RHYTHM — evening check-in is a wind-down read, not a morning to-do
# ===========================================================================
class RhythmGoldStandard(SimpleTestCase, GoldStandardMixin):
    @patch("apps.core.cos_briefing.daily_agenda._risk_clause", return_value="")
    @patch("apps.core.cos_briefing.daily_agenda._user_hour", return_value=21)
    @patch("apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items", return_value=[])
    @patch("apps.core.cos_briefing.rhythm_api.get_current_rhythm_item",
           return_value={"title": "Workout"})
    def test_evening_checkin_is_winddown(self, *_m):
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        a = build_daily_agenda(object())
        low = a.lower()
        self.assertNotIn("begin workout", low)
        self.assertNotIn("next up: workout", low)
        self.assertTrue(any(k in low for k in ("wind down", "winding down", "journal",
                                               "prepare for tomorrow", "sleep",
                                               "tomorrow's first priority", "rest up")))
        self.assertGreater(len(a), 60)                  # a real read, not a stub


# ===========================================================================
# EXECUTIVE — answered via the Goals strategic layer (per dependency graph);
# each must clear the gold gates and stay distinct.
# ===========================================================================
class ExecutiveGoldStandard(SimpleTestCase, GoldStandardMixin):
    # "what should I prioritize" -> goals_focus_today ; "what concerns you most" ->
    # biggest_goal_risk ; "what am I neglecting" -> goal_concerns ; "how am I doing
    # overall" -> goals_progress.
    def test_prioritize_is_one_concrete_action(self):
        a = stages._goals_focus_today_fallback(_gwm("goals_focus_today"))
        self.assert_gold(a, required=("today",))

    def test_concerns_most_is_a_real_risk_or_watch(self):
        a = stages._goal_risk_fallback(_gwm("biggest_goal_risk"))
        self.assert_gold(a, action=True, min_synthesis=2)

    def test_neglecting_filters_to_slipping(self):
        # all-healthy fixture -> honest "nothing slipping" (still specific + non-generic)
        a = stages._goal_concerns_fallback(_gwm("goal_concerns"))
        self.assertEqual(_banned_hits(a), [])
        self.assertIn("slipping", a.lower())
