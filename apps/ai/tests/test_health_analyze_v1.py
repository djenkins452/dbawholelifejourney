"""Health Analyze v1 — question differentiation, time-awareness, signal
prioritization, single-lever selection, bounded judgment. All deterministic."""

from datetime import datetime
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.cognitive_mode import health_analyze_v1 as v1


_HEALTH = {
    "weight_current": 289.9, "weight_unit": "lb", "weight_trend": "decreasing",
    "weight_change_30d": -3.8,
    "glucose_summary": {"trend_7d_vs_30d": "improving", "average_7d": 105,
                        "time_in_range_pct_7d": 72},
    "glucose_context": "Normal", "glucose_avg_7d": 105,
    "sleep_avg_hours_7d": 6.3, "sleep_trend": "stable",
    "sleep_consistency_score": 45,
    "body_composition": {
        "delta": {"waist": -0.5, "lean_mass": 0.2, "arm_left": 0.3},
        "largest_improvement": {"metric": "waist", "label": "Waist down 0.5 in"},
        "largest_regression": {},
    },
}
_FITNESS = {"workouts_7d": 4, "workout_adherence_score": 80}
_NUTRITION = {"protein_compliance_pct": 60}


def _ctx(hour=13, health=None, fitness=None, nutrition=None):
    """Patch SAE state + user-local time."""
    state = {"health": health if health is not None else _HEALTH,
             "fitness": fitness if fitness is not None else _FITNESS,
             "nutrition": nutrition if nutrition is not None else _NUTRITION}

    def _fake_state(user, module, *a, **k):
        return state.get(module, {})

    def _fake_now(user):
        return datetime(2026, 6, 8, hour, 0, 0)

    return mock.patch.multiple(
        "apps.core.ai_state.state_engine", get_module_state=mock.DEFAULT
    ), _fake_state, _fake_now


def _run(qmsg, hour=13, **state_over):
    with mock.patch("apps.core.ai_state.state_engine.get_module_state") as gms, \
         mock.patch("apps.core.utils.get_user_now") as now:
        s = {"health": state_over.get("health", _HEALTH),
             "fitness": state_over.get("fitness", _FITNESS),
             "nutrition": state_over.get("nutrition", _NUTRITION)}
        gms.side_effect = lambda u, m, *a, **k: s.get(m, {})
        now.side_effect = lambda u: datetime(2026, 6, 8, hour, 0, 0)
        return v1.build_health_analyze(object(), qmsg)


class ClassificationTests(SimpleTestCase):
    def test_question_typing(self):
        self.assertEqual(v1.classify_analyze_question("what do you think about my weight history?"), "weight_history")
        self.assertEqual(v1.classify_analyze_question("how am i doing overall with my health?"), "overall")
        self.assertEqual(v1.classify_analyze_question("what patterns do you notice lately?"), "patterns")
        self.assertEqual(v1.classify_analyze_question("do you think i need to change anything?"), "change_anything")
        self.assertEqual(v1.classify_analyze_question("am i losing weight too quickly?"), "pace_check")
        self.assertEqual(v1.classify_analyze_question("am i overtraining?"), "overtraining")

    def test_judgment_trigger(self):
        self.assertTrue(v1.is_health_judgment_request("am i losing weight too quickly?"))
        self.assertTrue(v1.is_health_judgment_request("am i overtraining?"))
        self.assertFalse(v1.is_health_judgment_request("what is my weight?"))


class DifferentiationTests(SimpleTestCase):
    def test_four_questions_produce_distinct_answers(self):
        wh = _run("what do you think about my weight history?")
        ov = _run("how am i doing overall with my health?")
        pa = _run("what patterns do you notice lately?")
        ch = _run("do you think i need to change anything?")
        outs = [wh, ov, pa, ch]
        for o in outs:
            self.assertTrue(o)
        # Pairwise distinct — no shared template.
        self.assertEqual(len(set(outs)), 4)

    def test_weight_history_shape(self):
        out = _run("what do you think about my weight history?")
        self.assertIn("sustainable", out.lower())
        self.assertIn("glucose", out.lower())
        self.assertNotIn("What I notice:", out)  # not the v0 bullet template

    def test_overall_is_holistic_not_weight_only(self):
        out = _run("how am i doing overall with my health?")
        self.assertIn("overall", out.lower())
        self.assertTrue("consistency" in out.lower() or "recovery" in out.lower())

    def test_patterns_is_observational(self):
        out = _run("what patterns do you notice lately?")
        self.assertIn("pattern", out.lower())


class SignalPrioritizationTests(SimpleTestCase):
    def test_arm_measurement_noise_not_surfaced(self):
        # body_composition has arm_left delta, but it must NEVER appear.
        for q in ("what do you think about my weight history?",
                  "how am i doing overall with my health?"):
            out = _run(q)
            self.assertNotIn("arm", out.lower())


class TimeAwarenessTests(SimpleTestCase):
    def test_morning_does_not_pick_protein_lever(self):
        # Morning + protein 0% must NOT yield a "behind on protein" lever.
        out = _run("do you think i need to change anything?", hour=7,
                   nutrition={"protein_compliance_pct": 0})
        self.assertNotIn("protein", out.lower())

    def test_evening_can_judge_protein(self):
        out = _run("do you think i need to change anything?", hour=20,
                   nutrition={"protein_compliance_pct": 40},
                   fitness={"workouts_7d": 4}, health={**_HEALTH, "sleep_consistency_score": 80, "sleep_avg_hours_7d": 7.2})
        # With sleep fine, protein under target in the evening becomes the lever.
        self.assertIn("protein", out.lower())


class LeverSelectionTests(SimpleTestCase):
    def test_not_always_protein(self):
        # Zero workouts should outrank protein as the lever.
        out = _run("do you think i need to change anything?", hour=20,
                   fitness={"workouts_7d": 0},
                   nutrition={"protein_compliance_pct": 40})
        self.assertIn("workout", out.lower())

    def test_no_lever_when_all_good(self):
        out = _run("do you think i need to change anything?", hour=20,
                   fitness={"workouts_7d": 5},
                   nutrition={"protein_compliance_pct": 95},
                   health={**_HEALTH, "sleep_avg_hours_7d": 7.5,
                           "sleep_consistency_score": 85, "sleep_trend": "stable"})
        self.assertIn("wouldn't change anything", out.lower())


class BoundedJudgmentTests(SimpleTestCase):
    def test_pace_sustainable(self):
        out = _run("am i losing weight too quickly?")
        self.assertIn("don't think you're losing too quickly", out.lower())

    def test_pace_fast(self):
        # -22 lb/30d ≈ 1.77%/week → above the 1.25% sustainable ceiling.
        out = _run("am i losing weight too quickly?",
                   health={**_HEALTH, "weight_change_30d": -22.0})
        self.assertIn("faster", out.lower())

    def test_overtraining_low_risk(self):
        out = _run("am i overtraining?", fitness={"workouts_7d": 3})
        self.assertIn("overtraining", out.lower())


class FallbackTests(SimpleTestCase):
    def test_no_data_returns_none(self):
        out = _run("what do you think about my weight history?",
                   health={}, fitness={}, nutrition={})
        self.assertIsNone(out)

    def test_disabled_returns_none(self):
        with self.settings(WLJ_BETH_HEALTH_ANALYZE_V1=False):
            out = _run("how am i doing overall?")
        self.assertIsNone(out)
