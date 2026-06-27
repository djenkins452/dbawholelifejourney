# ==============================================================================
# File: apps/ai/tests/test_beth_acceptance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: BETH PRODUCTION ACCEPTANCE SUITE — the validation questions Danny
#              regularly asks. Release is blocked if any of these fail. Asserts
#              correct routing, materially-distinct answers, expected/forbidden
#              concepts, no banned generic language, evening time-awareness, and
#              general-knowledge routing. Deterministic (no OpenAI).
# ==============================================================================
from unittest.mock import patch
from datetime import datetime

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod
from apps.ai.chatgpt_cos.reasoning import stages
from apps.ai.chatgpt_cos.p25_classifier import classify_request

MISSION = "France 2027 Family 18K Mission"

# A richly-defined France mission (milestones, why_it_matters, success, drivers).
_FRANCE_CTX = {
    "has_milestones": True,
    "current_phase": "Weight-loss foundation phase",
    "active_milestone": "Weight-loss foundation phase",
    "active_milestone_detail": "Reach 284.9 lb — protein target, hydration, and "
                               "scheduled workouts each day",
    "next_milestones": ["Return to running base"],
    "recently_completed_milestone": "Bought running shoes",
    "why_it_matters": "To run the 18K in France with my family and be healthy enough "
                      "to keep up with my kids for decades.",
    "success_definition": "Crossing the France 18K finish line together as a family in 2027.",
}
_FRANCE_EV = {
    "state": "stable", "momentum": "moderate", "trend": "stable",
    "phase": "Weight-loss foundation phase", "momentum_summary": "on pace",
    "success_drivers": ["weight trending down", "workouts on schedule"],
    "risk_drivers": ["workout frequency is light"],
    "recommended_action": "complete today's scheduled workout and hit your protein target",
    "as_of": "2026-06-25",
}
FRANCE = {
    "goals_state": {"state": {
        "active_goal_count": 3, "completion_rate": 0.4, "overdue_goal_count": 0,
        "active_titles": [
            {"title": MISSION, "target_date": None, "context": _FRANCE_CTX,
             "evidence": _FRANCE_EV},
            {"title": "Read 50 books", "target_date": None, "context": {"has_milestones": False},
             "evidence": {"state": "stable", "momentum": "moderate", "trend": "stable",
                          "momentum_summary": "on pace", "success_drivers": [],
                          "risk_drivers": [], "recommended_action": "read 20 pages today"}},
        ],
        "upcoming_titles": [], "overdue_titles": [],
        "mission": {"title": MISSION, "context": _FRANCE_CTX, "evidence": _FRANCE_EV},
    }},
    "habits_state": {"state": {"active_habit_count": 1, "avg_completion_rate": 0.6,
                               "streaks_per_habit": []}},
}


def _wm(intent):
    return {"intent": intent, "facts": stages.goals_working_memory(FRANCE)}


_FALLBACKS = {
    "goals_progress": stages._goals_progress_fallback,
    "goal_on_track": stages._goal_on_track_fallback,
    "goal_why_priority": stages._goal_why_priority_fallback,
    "goal_next_milestone": stages._goal_next_milestone_fallback,
    "goal_failure_modes": stages._goal_failure_modes_fallback,
    "goal_confidence": stages._goal_confidence_fallback,
}


# ===========================================================================
# FAILURE #2 — six distinct goal intents route correctly and answer distinctly
# ===========================================================================
class GoalIntentRoutingAcceptance(SimpleTestCase):
    QUESTIONS = {
        f"How is my {MISSION} progressing?": "goals_progress",
        f"Am I still on track for my {MISSION}?": "goal_on_track",
        f"Why is the {MISSION} my highest priority goal?": "goal_why_priority",
        f"What is the next milestone for my {MISSION}?": "goal_next_milestone",
        f"What could cause the {MISSION} to fail?": "goal_failure_modes",
        f"How confident are you that I'll achieve the {MISSION}?": "goal_confidence",
    }

    def test_each_question_routes_to_its_own_intent(self):
        for q, intent in self.QUESTIONS.items():
            got = planmod.named_goal_intent(q, [MISSION], MISSION)[0]
            self.assertEqual(got, intent, f"{q!r} routed to {got}, expected {intent}")

    def test_deictic_variants_route_too(self):
        cases = {
            "how is my mission going": "goals_progress",
            "am i on track with this goal": "goal_on_track",
            "why is this goal my priority": "goal_why_priority",
            "what's the next milestone for this goal": "goal_next_milestone",
            "what could make this mission fail": "goal_failure_modes",
            "how confident are you i'll hit this goal": "goal_confidence",
        }
        for q, intent in cases.items():
            self.assertEqual(planmod.named_goal_intent(q, [], None)[0], intent, q)

    def test_all_six_intents_registered(self):
        for intent in self.QUESTIONS.values():
            self.assertIn(intent, planmod.IMPLEMENTED_INTENTS)
            self.assertIn(intent, stages.INTENT_CURATORS)
            self.assertIn(intent, stages.REASONING_PROFILES)
            self.assertEqual(stages.INTENT_TRUTH_SCOPE[intent], stages.GOALS_TRUTH)


class GoalIntentAnswerDifferentiation(SimpleTestCase):
    def setUp(self):
        self.answers = {k: fb(_wm(k)) for k, fb in _FALLBACKS.items()}

    def test_six_answers_are_materially_distinct(self):
        vals = list(self.answers.values())
        self.assertEqual(len(set(vals)), 6, "intents collapsed to identical answers")
        # pairwise low overlap on first sentence
        firsts = [v.split(".")[0].lower() for v in vals]
        self.assertEqual(len(set(firsts)), 6, "intent openings are not distinct")

    def test_progress_is_a_status_summary(self):
        a = self.answers["goals_progress"].lower()
        self.assertIn(MISSION.lower(), a)
        self.assertTrue("momentum" in a or "phase" in a)

    def test_on_track_is_a_verdict(self):
        a = self.answers["goal_on_track"].lower()
        self.assertTrue(a.startswith("yes") or a.startswith("no") or "on track" in a
                        or "off track" in a or "roughly" in a)
        self.assertIn("next move", a)

    def test_why_priority_is_rationale_only(self):
        a = self.answers["goal_why_priority"]
        self.assertIn("family", a.lower())          # from why_it_matters
        # forbidden: portfolio/metadata
        for bad in ("active goal", "deadline", "completion", "% ", "momentum score"):
            self.assertNotIn(bad, a.lower(), f"why_priority leaked: {bad}")

    def test_next_milestone_is_milestone_only(self):
        a = self.answers["goal_next_milestone"]
        self.assertIn("Weight-loss foundation phase", a)
        self.assertIn("Return to running base", a)
        self.assertNotIn("Read 50 books", a)        # never another goal

    def test_failure_modes_is_failure_analysis(self):
        a = self.answers["goal_failure_modes"].lower()
        self.assertIn("fail", a)
        self.assertTrue(any(k in a for k in ("workout", "nutrition", "consistency",
                                             "momentum", "routine")))
        self.assertNotIn("you have 3 active goal", a)   # not a progress summary

    def test_confidence_is_a_confidence_read(self):
        a = self.answers["goal_confidence"].lower()
        self.assertIn("confiden", a)
        self.assertTrue(any(k in a for k in ("high", "solid", "moderate", "low")))


# ===========================================================================
# FAILURE #3 — focus / recommendations never contain banned generic language
# ===========================================================================
class NoBannedLanguageAcceptance(SimpleTestCase):
    def _all_focus_outputs(self):
        outs = [stages._goals_focus_today_fallback(_wm("goals_focus_today"))]
        # also the action embedded in every differentiated intent
        for k, fb in _FALLBACKS.items():
            outs.append(fb(_wm(k)))
        return [o.lower() for o in outs]

    def test_no_banned_phrase_anywhere(self):
        for out in self._all_focus_outputs():
            for banned in stages._BANNED_FOCUS:
                self.assertNotIn(banned, out, f"banned phrase leaked: {banned!r}")

    def test_focus_is_a_concrete_action(self):
        out = stages._goals_focus_today_fallback(_wm("goals_focus_today")).lower()
        self.assertTrue("workout" in out or "protein" in out or "milestone" in out)


# ===========================================================================
# FAILURE #1 — evening check-in is time-aware (no morning activities at night)
# ===========================================================================
class EveningCheckInAcceptance(SimpleTestCase):
    @patch("apps.core.cos_briefing.daily_agenda._risk_clause", return_value="")
    @patch("apps.core.cos_briefing.daily_agenda._user_hour", return_value=21)
    @patch("apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items", return_value=[])
    @patch("apps.core.cos_briefing.rhythm_api.get_current_rhythm_item",
           return_value={"title": "Workout"})
    def test_9pm_agenda_does_not_start_morning_activity(self, *_mocks):
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        out = build_daily_agenda(object())
        low = out.lower()
        self.assertNotIn("begin workout", low)
        self.assertNotIn("next up: workout", low)
        self.assertNotIn("best next step is to begin", low)
        self.assertTrue(any(k in low for k in ("sleep", "wind down", "winding down",
                                               "journal", "prepare for tomorrow",
                                               "tomorrow's first priority", "rest up")))

    @patch("apps.core.cos_briefing.daily_agenda._risk_clause", return_value="")
    @patch("apps.core.cos_briefing.daily_agenda._focus_now_title", return_value="Workout")
    @patch("apps.core.cos_briefing.daily_agenda._user_hour", return_value=9)
    @patch("apps.core.cos_briefing.rhythm_api.get_remaining_rhythm_items",
           return_value=[{"title": "Workout", "time": "07:00"}])
    @patch("apps.core.cos_briefing.rhythm_api.get_current_rhythm_item",
           return_value={"title": "Workout"})
    def test_morning_agenda_still_drives_the_day(self, *_mocks):
        from apps.core.cos_briefing.daily_agenda import build_daily_agenda
        out = build_daily_agenda(object()).lower()
        # daytime keeps action framing (not evening wind-down)
        self.assertNotIn("rest up tonight", out)


# ===========================================================================
# FAILURE #4 — general-knowledge questions route to the general lane (EXTERNAL)
# ===========================================================================
class GeneralKnowledgeRoutingAcceptance(SimpleTestCase):
    GENERAL = ("Who was Abraham Lincoln?", "What was the Oracle of Delphi?",
               "Explain photosynthesis.")

    def test_general_questions_classify_external(self):
        for q in self.GENERAL:
            self.assertEqual(classify_request(q)["classification"], "EXTERNAL", q)

    def test_general_questions_not_stolen_by_goal_prerouter(self):
        # No goal title / deictic -> the goal pre-router must NOT claim them.
        for q in self.GENERAL:
            self.assertIsNone(planmod.named_goal_intent(q, [MISSION], MISSION)[0], q)

    def test_general_questions_look_general(self):
        from apps.ai.chatgpt_cos.lanes import _looks_general
        for q in self.GENERAL:
            self.assertTrue(_looks_general(q), q)

    def test_general_call_bypasses_circuit_breaker(self):
        # The foreground general call must attempt OpenAI even if the breaker is
        # set (Failure #4 reliability) — proven by the bypass_breaker kwarg.
        from django.core.cache import cache
        captured = {}

        def _fake_call_api(system, message, **kw):
            captured.update(kw)
            return "Abraham Lincoln was the 16th U.S. president."

        cache.set("openai_rate_limited", True, timeout=60)
        try:
            with patch("apps.ai.services.ai_service._call_api", side_effect=_fake_call_api):
                from apps.ai.chatgpt_cos.lanes import general_answer
                res = general_answer(object(), "Who was Abraham Lincoln?")
        finally:
            cache.delete("openai_rate_limited")
        self.assertTrue(captured.get("bypass_breaker") is True)
        self.assertIn("Lincoln", res["answer"])
