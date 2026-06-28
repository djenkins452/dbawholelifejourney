# ==============================================================================
# File: apps/ai/tests/test_cos_acceptance.py
# Description: Chief-of-Staff Acceptance Suite — the layer ABOVE Deep. Pure-function
#   tests for the Deep dependency gate, the weighted rubric scorer, scenario grading,
#   and the Law-tied report. "Would an exceptional human Chief of Staff have done
#   better?" — graded deterministically.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import cos_acceptance as cos


def _s(sid):
    return next(s for s in cos.COS_SCENARIOS if s["id"] == sid)


class DeepDependencyTests(SimpleTestCase):
    def test_cos_runs_only_when_deep_green(self):
        self.assertTrue(cos.cos_enabled("GREEN"))
        for g in ("RED", "YELLOW", "", None):
            self.assertFalse(cos.cos_enabled(g))

    def test_disabled_reason_explains_and_directs(self):
        self.assertIn("run Deep", cos.disabled_reason(""))
        self.assertIn("Deep is RED", cos.disabled_reason("RED"))
        self.assertEqual(cos.disabled_reason("GREEN"), "")


class ScenarioLibraryTests(SimpleTestCase):
    REQUIRED = ("cos_good_morning_stale_sleep", "cos_workout_answered_with_sleep",
                "cos_deterministic_retrieval_failure", "cos_medication_education",
                "cos_cgm_false_low_investigation", "cos_goal_coaching",
                "cos_daily_planning", "cos_weight_trend_discussion")

    def test_seed_scenarios_present_and_well_formed(self):
        ids = {s["id"] for s in cos.COS_SCENARIOS}
        for r in self.REQUIRED:
            self.assertIn(r, ids)
        for s in cos.COS_SCENARIOS:
            self.assertTrue(s["question"] and s["law"] and s["capability"]
                            and s["classification"] and s["why"], s["id"])

    def test_scenarios_is_appendable_for_regression(self):
        # New production conversations become permanent scenarios (a plain list).
        self.assertIsInstance(cos.scenarios(), list)


class RubricScoringTests(SimpleTestCase):
    def test_weights_sum_to_one_and_hard_fail_dims(self):
        self.assertAlmostEqual(sum(cos.WEIGHTS.values()), 1.0, places=3)
        self.assertEqual(cos.HARD_FAIL_DIMENSIONS, ("trust", "intent"))

    def test_stale_sleep_chatbot_vs_chief_of_staff(self):
        s = _s("cos_good_morning_stale_sleep")
        bad = cos.score_response(s, "Good morning! You slept 6.9 hours last night.")
        good = cos.score_response(s, "Good morning. I don't have last night's sleep "
                                  "yet — Apple Health hasn't synced; I'll have it once it syncs.")
        self.assertEqual(bad["grade"], "RED")
        self.assertTrue(bad["hard_fail"])      # presenting stale-as-current = trust break
        self.assertEqual(good["grade"], "GREEN")

    def test_wrong_domain_is_hard_intent_fail(self):
        s = _s("cos_workout_answered_with_sleep")
        bad = cos.score_response(s, "You slept 6.9 hours last night.")
        good = cos.score_response(s, "You haven't worked out today — no workout logged yet.")
        self.assertTrue(bad["hard_fail"])
        self.assertIn("intent", bad["failures"])
        self.assertEqual(good["grade"], "GREEN")

    def test_deterministic_ai_failure_breaks_trust(self):
        s = _s("cos_deterministic_retrieval_failure")
        bad = cos.score_response(s, "my external knowledge service is temporarily unavailable")
        good = cos.score_response(s, "You got 8,123 steps yesterday.")
        self.assertEqual(bad["grade"], "RED")
        self.assertTrue(bad["hard_fail"])
        self.assertEqual(good["grade"], "GREEN")

    def test_cgm_expectation_matching(self):
        s = _s("cos_cgm_false_low_investigation")
        bad = cos.score_response(s, "Your blood sugar is dangerously low. Treat the low immediately.")
        good = cos.score_response(s, "A 45 right after pizza doesn't quite fit what I'd "
                                  "expect — that can be a compression low or sensor artifact. "
                                  "I'd verify with a finger stick before treating.")
        self.assertTrue(bad["hard_fail"])
        self.assertEqual(good["grade"], "GREEN")

    def test_coaching_cliche_fails(self):
        s = _s("cos_goal_coaching")
        bad = cos.score_response(s, "Just maintain momentum and stay consistent — you've got this!")
        self.assertIn("coaching", bad["failures"])
        good = cos.score_response(s, "You're behind pace on the France 18K. This week, "
                                  "schedule three training runs and add a mile to your long run.")
        self.assertEqual(good["grade"], "GREEN")


class GradeAndReportTests(SimpleTestCase):
    def test_grade_run_any_hard_fail_is_red(self):
        scored = [{"weighted": 1.0, "hard_fail": False},
                  {"weighted": 1.0, "hard_fail": True}]
        self.assertEqual(cos.grade_run(scored)["grade"], "RED")
        self.assertEqual(cos.grade_run(scored)["hard_fails"], 1)
        allgood = [{"weighted": 0.95, "hard_fail": False}]
        self.assertEqual(cos.grade_run(allgood)["grade"], "GREEN")

    def test_report_ties_failures_to_laws_and_capabilities(self):
        pairs = [
            (_s("cos_workout_answered_with_sleep"), "You slept 6.9 hours."),       # chatbot
            (_s("cos_deterministic_retrieval_failure"), "temporarily unavailable"),  # chatbot
            (_s("cos_good_morning_stale_sleep"),
             "I don't have last night's sleep yet — hasn't synced; I'll have it once it "
             "syncs. Worth a glance at Apple Health."),                              # CoS
        ]
        rep = cos.build_report(pairs)
        self.assertEqual(rep["grade"], "RED")  # hard fails present
        self.assertIn("cos_good_morning_stale_sleep", rep["first_class"])
        self.assertEqual(set(rep["behaved_like_chatbot"]),
                         {"cos_workout_answered_with_sleep", "cos_deterministic_retrieval_failure"})
        # Grouped by capability classification → guides engineering priorities.
        self.assertIn("Retrieval", rep["priority_by_capability"])
        # Each chatbot entry carries the 5 required report facets.
        e = next(x for x in rep["entries"] if x["id"] == "cos_workout_answered_with_sleep")
        self.assertTrue(e["what_happened"] and e["why_it_matters"]
                        and e["law_violated"] and e["missing_capability"] and e["classification"])
