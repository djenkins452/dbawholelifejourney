"""
Deterministic tests for Body Intelligence whole-journey interpretation.

Pins:
  1. `analyze_trajectory` — baseline (first reading) → overall + rolling recent.
  2. `build_body_assessment` — ONE holistic verdict (overall + recent), incl. RECOVERING
     when lean is below baseline but rebuilding.
  3. `interpret_measurement` — FACTS + interpretation from the assessment; overall drives the
     status (noise-resistant), Recovering when overall is behind but recent is correcting.
  4. `build_insights` — generated FROM the rows so Insights can never contradict a card.
"""
from datetime import date, timedelta

from django.test import SimpleTestCase

from apps.health.services.measurement_interpretation import (
    IMPROVING, RECOVERING, NEEDS_ATTENTION, STABLE, INCONCLUSIVE,
    analyze_trajectory, build_body_assessment, interpret_measurement, build_insights,
)


def _series(values, step_days=7):
    start = date(2026, 1, 1)
    return [{"date": (start + timedelta(days=i * step_days)).isoformat(), "value": float(v)}
            for i, v in enumerate(values)]


def _traj(overall, recent=0.0):
    return {"baseline": 0.0, "latest": overall, "overall": overall, "recent": recent,
            "n": 10, "span_days": 90}


class AnalyzeTrajectoryTests(SimpleTestCase):
    def test_overall_and_recent(self):
        t = analyze_trajectory(_series([60, 59, 58, 57, 56, 55, 54, 53, 52, 51]), "in")
        self.assertEqual(t["overall"], -9.0)
        self.assertLess(t["recent"], 0)
        self.assertNotEqual(t["recent"], t["overall"])

    def test_needs_two_readings(self):
        self.assertIsNone(analyze_trajectory(_series([50]), "in"))


class BuildBodyAssessmentTests(SimpleTestCase):
    def test_recomposition_is_improving(self):
        a = build_body_assessment(fat_traj=_traj(-5.0), lean_traj=_traj(3.0))
        self.assertEqual(a["status"], IMPROVING)

    def test_lean_below_baseline_but_rebuilding_is_recovering(self):
        # The screenshot case: lean overall -12, recently +2.8 → Recovering, NOT muscle loss.
        a = build_body_assessment(fat_traj=_traj(-14.0, -7.4), lean_traj=_traj(-12.0, 2.8))
        self.assertEqual(a["status"], RECOVERING)
        self.assertEqual(a["verdict"], "recovering")
        self.assertIn("rebuilding", a["summary"])

    def test_lean_still_falling_needs_attention(self):
        a = build_body_assessment(fat_traj=_traj(-0.5), lean_traj=_traj(-4.0, -0.6))
        self.assertEqual(a["status"], NEEDS_ATTENTION)

    def test_fat_loss_preserving_is_improving(self):
        a = build_body_assessment(fat_traj=_traj(-5.0), lean_traj=_traj(0.2))
        self.assertEqual(a["status"], IMPROVING)

    def test_no_history_is_inconclusive(self):
        self.assertEqual(build_body_assessment()["status"], INCONCLUSIVE)


class InterpretMeasurementTests(SimpleTestCase):
    A_IMPROVING = {"status": IMPROVING, "confidence": "high",
                   "evidence": ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"],
                   "summary": "you're losing fat and building lean mass"}
    A_RECOVERING = {"status": RECOVERING, "confidence": "high",
                    "evidence": ["Lean mass ↓ over your journey", "Lean mass ↑ recently"],
                    "summary": "you lost lean mass earlier but recent readings show you rebuilding it"}
    A_ATTENTION = {"status": NEEDS_ATTENTION, "confidence": "high",
                   "evidence": ["Lean mass ↓ over your journey"],
                   "summary": "your lean mass is below your starting point"}

    # Direct measures
    def test_waist_overall_down_is_improving(self):
        r = interpret_measurement("waist", "in", _traj(-6.2, -0.5), None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("Down", r["overall_text"])

    def test_lean_below_start_but_rebuilding_is_recovering(self):
        # Direct lean card: overall Down 12, Recent Up 2.8 → Recovering (matches user example).
        r = interpret_measurement("lean_mass", "lb", _traj(-12.0, 2.8), None)
        self.assertEqual(r["status"], RECOVERING)
        self.assertEqual(r["status_label"], "Recovering")
        self.assertIn("rebuilding", r["reason"].lower())

    def test_overall_flat_is_stable(self):
        self.assertEqual(interpret_measurement("waist", "in", _traj(0.1, 0.0), None)["status"], STABLE)

    def test_overall_and_recent_away_needs_attention(self):
        self.assertEqual(interpret_measurement("lean_mass", "lb", _traj(-5.0, -0.7), None)["status"],
                         NEEDS_ATTENTION)

    # Limbs read against the ONE assessment
    def test_limb_under_recovering_is_recovering_not_red(self):
        # The screenshot fix: a shrinking thigh while the body is RECOVERING must not read red.
        r = interpret_measurement("thigh_left", "in", _traj(-1.5, -0.38), self.A_RECOVERING)
        self.assertEqual(r["status"], RECOVERING)
        self.assertNotEqual(r["status"], NEEDS_ATTENTION)

    def test_limb_up_under_recomposition_is_muscle(self):
        r = interpret_measurement("arm_left", "in", _traj(0.4, 0.1), self.A_IMPROVING)
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("muscle", r["reason"].lower())

    def test_limb_shrinking_under_muscle_loss_needs_attention(self):
        r = interpret_measurement("calf_left", "in", _traj(-0.6, -0.2), self.A_ATTENTION)
        self.assertEqual(r["status"], NEEDS_ATTENTION)

    def test_limb_flat_is_stable(self):
        self.assertEqual(
            interpret_measurement("calf_left", "in", _traj(0.1, 0.0), self.A_RECOVERING)["status"], STABLE)

    def test_neutral_flat_is_stable(self):
        self.assertEqual(interpret_measurement("chest", "in", _traj(0.1, 0.0), None)["status"], STABLE)

    def test_no_history_is_inconclusive(self):
        self.assertEqual(interpret_measurement("waist", "in", None, None)["status"], INCONCLUSIVE)


class BuildInsightsTests(SimpleTestCase):
    def test_insights_generated_from_rows_and_ordered(self):
        rows = [
            {"label": "Waist", "status": IMPROVING, "status_label": "Improving", "overall_text": "Down 6.2 in"},
            {"label": "Lean Mass", "status": RECOVERING, "status_label": "Recovering", "overall_text": "Down 12 lb"},
            {"label": "Arm", "status": NEEDS_ATTENTION, "status_label": "Needs attention", "overall_text": "Down 1 in"},
            {"label": "Calf", "status": STABLE, "status_label": "Stable", "overall_text": "Flat"},
        ]
        out = build_insights(rows)
        # Attention first, then recovering, then improving, then stable.
        self.assertTrue(out[0].startswith("Arm: Needs attention"))
        self.assertTrue(out[1].startswith("Lean Mass: Recovering"))
        self.assertIn("Waist: Improving", out[2])
        # Every insight mirrors a card's status → cannot contradict.
        self.assertTrue(all("—" in line for line in out))
