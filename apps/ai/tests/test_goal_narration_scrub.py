# ==============================================================================
# File: apps/ai/tests/test_goal_narration_scrub.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Narration defect class — legacy generic coaching language must NEVER
#   leak through DETERMINISTIC goal narration (e.g. a user's own milestone
#   description "Lock in consistency with protein…" echoed verbatim). Validates the
#   ACTUAL rendered fallback responses through the real curator, not template
#   strings. Origin: production Full run flagged `banned_phrase: lock in consistency`
#   on goal_next_milestone.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.reasoning import stages

# Every goal intent that has a deterministic fallback.
_GOAL_INTENTS = ("biggest_goal_risk", "goals_progress", "goals_focus_today",
                 "goal_concerns", "goal_on_track", "goal_why_priority",
                 "goal_next_milestone", "goal_failure_modes", "goal_confidence")

# A goal whose USER FREE-TEXT (milestone detail, recommended action, why-it-matters,
# success definition) is saturated with the exact coaching phrases the gate bans —
# this is the real France milestone wording that produced the production failure.
_CONTAMINATED_CONTEXT = {
    "current_phase": "Momentum phase",
    "active_milestone_detail": ("Momentum phase. Lock in consistency with protein, "
                                "hydration, workouts, meds, and routine execution."),
    "next_milestones": ["Goal Weight 279.9"],
    "why_it_matters": "Stay consistent and maintain momentum for the family trip.",
    "success_definition": "Keep it up and you've got this — reach 18K steps in France.",
    "has_milestones": True,
}
_CONTAMINATED_EVIDENCE = {
    "state": "stable", "momentum": "moderate", "trend": "stable",
    "phase": "Momentum phase", "momentum_summary": "on pace",
    "success_drivers": ["weight trending down", "exercise consistency"],
    "risk_drivers": ["workout frequency is light"],
    "recommended_action": "Lock in consistency with protein and hydration.",
    "as_of": "2026-06-25",
}
_CONTAMINATED_FIXTURE = {
    "goals_state": {"state": {
        "active_goal_count": 1, "completion_rate": 0.42, "overdue_goal_count": 0,
        "active_titles": [{"title": "France 2027 Family 18K Mission",
                           "target_date": None, "is_foundational": True,
                           "evidence": _CONTAMINATED_EVIDENCE,
                           "context": _CONTAMINATED_CONTEXT}],
        "upcoming_titles": [], "overdue_titles": [],
        "mission": {"title": "France 2027 Family 18K Mission",
                    "current_focus": "Momentum phase", "momentum_trend": "stable",
                    "days_remaining": None, "evidence": _CONTAMINATED_EVIDENCE,
                    "context": _CONTAMINATED_CONTEXT},
    }},
    "habits_state": {"state": {
        "active_habit_count": 1, "avg_completion_rate": 0.7, "longest_streak": 6,
        "streaks_per_habit": [{"name": "Workout", "at_risk": False, "current_streak": 6}],
    }},
}


class GoalNarrationScrubTests(SimpleTestCase):
    def _wm(self):
        facts = stages.goals_working_memory(_CONTAMINATED_FIXTURE)
        return {"facts": facts}

    def test_curator_strips_coaching_from_echoed_user_text(self):
        facts = stages.goals_working_memory(_CONTAMINATED_FIXTURE)
        ev = facts["goal_evidence"][0]
        for field in ("current_milestone_detail", "recommended_action",
                      "why_it_matters", "success_looks_like"):
            self.assertEqual(ar.banned_hits(ev.get(field, "")), [],
                             f"{field} leaked coaching: {ev.get(field)!r}")
        # substance preserved — the concrete specifics survive the scrub
        self.assertIn("protein", ev.get("current_milestone_detail", "").lower())

    def test_no_goal_fallback_leaks_banned_phrases(self):
        wm = self._wm()
        for intent in _GOAL_INTENTS:
            fb = stages.REASONING_PROFILES[intent]["fallback"]
            out = fb(wm)
            self.assertTrue(out and out.strip(), f"{intent} produced empty output")
            self.assertEqual(ar.banned_hits(out), [],
                             f"{intent} fallback leaked: {out!r}")

    def test_milestone_fallback_specifically_clean_and_useful(self):
        # the originally-reported failure: goal_next_milestone + "lock in consistency"
        out = stages._goal_next_milestone_fallback(self._wm())
        self.assertNotIn("lock in consistency", out.lower())
        self.assertIn("milestone", out.lower())          # still answers the question
        self.assertIn("protein", out.lower())            # keeps the concrete detail


class ScrubCoachingUnitTests(SimpleTestCase):
    def test_keeps_substance_drops_coaching(self):
        out = stages._scrub_coaching(
            "Momentum phase. Lock in consistency with protein, hydration, workouts.")
        self.assertEqual(ar.banned_hits(out), [])
        self.assertIn("protein", out.lower())

    def test_pure_coaching_becomes_empty(self):
        for s in ("Lock in consistency.", "Maintain momentum and stay consistent.",
                  "Keep it up — you've got this!"):
            self.assertEqual(stages._scrub_coaching(s), "")

    def test_clean_text_unchanged_in_substance(self):
        s = "Reach 284.9 lb by completing scheduled workouts."
        self.assertEqual(ar.banned_hits(stages._scrub_coaching(s)), [])
        self.assertIn("284.9", stages._scrub_coaching(s))

    def test_blocklist_is_superset_of_acceptance_coaching(self):
        for phrase in ar.COACHING_BANNED:
            scrubbed = stages._scrub_coaching(f"Reach the target {phrase} with protein.")
            self.assertEqual(ar.banned_hits(scrubbed), [], f"{phrase!r} survived scrub")
