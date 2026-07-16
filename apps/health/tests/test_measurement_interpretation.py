"""
Deterministic tests for Body Intelligence WHOLE-JOURNEY measurement interpretation.

Pins:
  1. `analyze_trajectory` — baseline (first reading) → latest overall change + rolling recent.
  2. `classify_body_journey` — the body's overall trajectory from fat/lean/weight history.
  3. `interpret_measurement` — status driven by the OVERALL trend (noise-resistant), with a
     coach-style narrative; limbs read against the body's journey; flat-over-journey → Stable;
     not-enough-history → Inconclusive.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.health.services.measurement_interpretation import (
    IMPROVING, NEEDS_ATTENTION, STABLE, INCONCLUSIVE,
    analyze_trajectory, classify_body_journey, interpret_measurement,
)


def _series(values, step_days=7):
    """Weekly [{date,value}] history, oldest first."""
    start = date(2026, 1, 1)
    return [{"date": (start + timedelta(days=i * step_days)).isoformat(), "value": float(v)}
            for i, v in enumerate(values)]


def _traj(overall, recent=0.0):
    """A pre-analyzed trajectory dict for interpret/journey tests."""
    return {"baseline": 0.0, "latest": overall, "overall": overall, "recent": recent,
            "n": 10, "span_days": 90}


class AnalyzeTrajectoryTests(SimpleTestCase):
    def test_overall_and_recent_from_full_history(self):
        t = analyze_trajectory(_series([60, 59, 58, 57, 56, 55, 54, 53, 52, 51]), "in")
        self.assertEqual(t["baseline"], 60.0)
        self.assertEqual(t["latest"], 51.0)
        self.assertEqual(t["overall"], -9.0)          # baseline → latest
        self.assertLess(t["recent"], 0)               # still dropping recently
        self.assertGreater(t["overall"], t["recent"] - 100)  # sanity
        self.assertNotEqual(t["recent"], t["overall"])  # recent window ≠ whole journey

    def test_needs_two_readings(self):
        self.assertIsNone(analyze_trajectory(_series([50]), "in"))
        self.assertIsNone(analyze_trajectory([], "in"))


class ClassifyBodyJourneyTests(SimpleTestCase):
    def test_recomposition_is_improving(self):
        bj = classify_body_journey(fat_traj=_traj(-5.0), lean_traj=_traj(3.0))
        self.assertEqual(bj["status"], IMPROVING)
        self.assertIn("Lean mass ↑ over your journey", bj["evidence"])

    def test_fat_loss_preserving_is_improving(self):
        bj = classify_body_journey(fat_traj=_traj(-5.0), lean_traj=_traj(0.2))
        self.assertEqual(bj["status"], IMPROVING)

    def test_lean_loss_needs_attention(self):
        bj = classify_body_journey(fat_traj=_traj(-0.5), lean_traj=_traj(-3.0))
        self.assertEqual(bj["status"], NEEDS_ATTENTION)

    def test_conflicting_is_inconclusive(self):
        bj = classify_body_journey(fat_traj=_traj(2.0), lean_traj=_traj(2.0))
        self.assertEqual(bj["status"], INCONCLUSIVE)

    def test_no_history_is_inconclusive(self):
        self.assertEqual(classify_body_journey()["status"], INCONCLUSIVE)


class InterpretMeasurementTests(SimpleTestCase):
    BJ_IMPROVING = {"status": IMPROVING, "confidence": "high",
                    "evidence": ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"],
                    "summary": "you're losing fat and building muscle"}
    BJ_ATTENTION = {"status": NEEDS_ATTENTION, "confidence": "high",
                    "evidence": ["Lean mass ↓ over your journey"],
                    "summary": "lean mass has fallen over your journey"}
    BJ_LOW = {"status": INCONCLUSIVE, "confidence": "low", "evidence": [], "summary": "unclear"}

    # ── Direct measures — judged by the whole-journey overall trend ──
    def test_waist_overall_down_is_improving(self):
        r = interpret_measurement("waist", "in", _traj(-6.2, -0.5), None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("Down", r["overall_text"])
        self.assertIn("progress", r["reason"].lower())

    def test_waist_overall_down_recent_plateau_still_improving(self):
        r = interpret_measurement("waist", "in", _traj(-6.2, 0.0), None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("plateaued", r["reason"].lower())

    def test_waist_overall_flat_is_stable(self):
        r = interpret_measurement("waist", "in", _traj(0.1, 0.0), None)
        self.assertEqual(r["status"], STABLE)
        self.assertEqual(r["overall_text"], "Flat")

    def test_waist_overall_up_needs_attention(self):
        r = interpret_measurement("waist", "in", _traj(2.0, 0.3), None)
        self.assertEqual(r["status"], NEEDS_ATTENTION)

    def test_lean_mass_overall_up_is_improving(self):
        r = interpret_measurement("lean_mass", "lb", _traj(5.0, 0.6), None)
        self.assertEqual(r["status"], IMPROVING)

    def test_lean_mass_overall_down_needs_attention(self):
        r = interpret_measurement("lean_mass", "lb", _traj(-3.0, -0.4), None)
        self.assertEqual(r["status"], NEEDS_ATTENTION)

    # ── Limbs — read against the body's journey ──
    def test_arm_up_during_recomposition_is_muscle(self):
        r = interpret_measurement("arm_left", "in", _traj(0.4, 0.1), self.BJ_IMPROVING)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("muscle development", r["reason"].lower())
        self.assertIn("Lean mass ↑ over your journey", r["evidence"])

    def test_thigh_down_during_fat_loss_is_improving(self):
        r = interpret_measurement("thigh_left", "in", _traj(-0.8, -0.1), self.BJ_IMPROVING)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("fat loss", r["reason"].lower())

    def test_limb_shrinking_during_muscle_loss_needs_attention(self):
        r = interpret_measurement("calf_left", "in", _traj(-0.6, -0.2), self.BJ_ATTENTION)
        self.assertEqual(r["status"], NEEDS_ATTENTION)
        self.assertIn("muscle loss", r["reason"].lower())

    def test_limb_flat_over_journey_is_stable(self):
        r = interpret_measurement("calf_left", "in", _traj(0.1, 0.0), self.BJ_IMPROVING)
        self.assertEqual(r["status"], STABLE)
        self.assertIn("no meaningful long-term change", r["reason"].lower())

    def test_limb_with_unclear_body_is_inconclusive(self):
        r = interpret_measurement("forearm_left", "in", _traj(0.4, 0.1), self.BJ_LOW)
        self.assertEqual(r["status"], INCONCLUSIVE)

    # ── Neutral + no-history ──
    def test_neutral_flat_is_stable(self):
        r = interpret_measurement("chest", "in", _traj(0.1, 0.0), None)
        self.assertEqual(r["status"], STABLE)

    def test_no_history_is_inconclusive(self):
        r = interpret_measurement("waist", "in", None, None)
        self.assertEqual(r["status"], INCONCLUSIVE)
        self.assertIn("keep logging", r["reason"].lower())
