"""
Deterministic tests for Body Intelligence — Facts → one Assessment → per-card interpretation.

Pins:
  1. `build_body_assessment` — ONE executive verdict (grade/headline/facts/opportunity) from the
     whole-journey trajectories (overall + recent), incl. RECOVERING.
  2. `interpret_measurement` — every measurement CONTRIBUTES (no "no goal"); status derives from
     the assessment; overall drives it, recent adds Recovering.
  3. `build_insights` — generated FROM the rows → can never contradict a card.
"""
from django.test import SimpleTestCase

from apps.health.services.measurement_interpretation import (
    IMPROVING, RECOVERING, NEEDS_ATTENTION, STABLE, INCONCLUSIVE,
    build_body_assessment, interpret_measurement, build_insights,
)


def _T(overall, recent=0.0):
    return {"baseline": 0.0, "latest": overall, "overall": overall, "recent": recent,
            "n": 10, "span_days": 120}


class BuildBodyAssessmentTests(SimpleTestCase):
    def test_recovering_scenario_grade_and_facts(self):
        # Screenshot case: big fat loss, lean below start but rebuilding.
        a = build_body_assessment(
            {"fat_mass": _T(-14, -7.4), "lean_mass": _T(-12, 2.8), "waist": _T(-6.2, -0.5),
             "body_fat_pct": _T(-1.5, -2.0)},
            weight_traj=_T(-27, -1.0),
        )
        self.assertEqual(a["status"], RECOVERING)
        self.assertEqual(a["grade"], "Excellent")          # big fat loss
        self.assertTrue(any("Weight ↓ 27" in f for f in a["facts"]))
        self.assertTrue(any("Waist ↓ 6.2" in f for f in a["facts"]))
        self.assertTrue(any("recovering" in f.lower() for f in a["facts"]))
        # Executive story fields: narrative (why), wins, focus (what next), confidence basis.
        self.assertTrue(a["headline"] and a["narrative"] and a["wins"])
        self.assertTrue(any("lean" in f.lower() or "protein" in f.lower() for f in a["focus"]))
        self.assertIn("check-ins", a["confidence_basis"])

    def test_recomposition_is_excellent(self):
        a = build_body_assessment({"fat_mass": _T(-6), "lean_mass": _T(3)})
        self.assertEqual(a["status"], IMPROVING)
        self.assertEqual(a["grade"], "Excellent")

    def test_muscle_loss_needs_attention(self):
        a = build_body_assessment({"fat_mass": _T(-0.5), "lean_mass": _T(-4, -0.6)})
        self.assertEqual(a["status"], NEEDS_ATTENTION)
        self.assertEqual(a["grade"], "Needs attention")

    def test_no_history_is_getting_started(self):
        a = build_body_assessment({})
        self.assertEqual(a["status"], INCONCLUSIVE)
        self.assertEqual(a["grade"], "Getting started")


class InterpretMeasurementTests(SimpleTestCase):
    A_IMPROVING = {"status": IMPROVING, "confidence": "high",
                   "evidence": ["Body fat ↓ over your journey", "Lean mass ↑ over your journey"],
                   "summary": "you're losing fat and building lean mass"}
    A_RECOVERING = {"status": RECOVERING, "confidence": "high",
                    "evidence": ["Lean mass ↓ over your journey", "Lean mass ↑ recently"],
                    "summary": "you lost lean mass earlier but recent readings show you rebuilding it"}
    A_ATTENTION = {"status": NEEDS_ATTENTION, "confidence": "high", "evidence": [],
                   "summary": "your lean mass is below your starting point"}

    def test_lean_below_start_but_rebuilding_is_recovering(self):
        r = interpret_measurement("lean_mass", "lb", _T(-12, 2.8), None)
        self.assertEqual(r["status"], RECOVERING)
        self.assertIn("rebuilding", r["reason"].lower())

    def test_waist_improving(self):
        self.assertEqual(interpret_measurement("waist", "in", _T(-6.2, -0.5), None)["status"], IMPROVING)

    def test_limb_under_recovering_is_not_red(self):
        r = interpret_measurement("thigh_left", "in", _T(-1.5, -0.38), self.A_RECOVERING)
        self.assertEqual(r["status"], RECOVERING)

    def test_chest_now_participates_no_more_no_goal(self):
        # Chest is a circumference — interpreted against the assessment, never "no goal".
        r = interpret_measurement("chest", "in", _T(-1.0, -0.2), self.A_IMPROVING)
        self.assertNotEqual(r["status_label"], "No goal")
        self.assertEqual(r["status"], IMPROVING)
        self.assertIn("fat loss", r["reason"].lower())

    def test_bmr_supporting_participates_no_more_no_goal(self):
        r = interpret_measurement("bmr", "kcal/day", _T(-120, -20), self.A_RECOVERING)
        self.assertNotIn("no goal", r["reason"].lower())
        self.assertNotIn("no health goal", r["reason"].lower())
        self.assertEqual(r["status"], RECOVERING)     # mirrors the assessment as supporting evidence
        self.assertEqual(r["confidence"], "low")

    def test_flat_is_stable(self):
        self.assertEqual(interpret_measurement("chest", "in", _T(0.1, 0.0), self.A_IMPROVING)["status"], STABLE)

    def test_no_history_is_inconclusive(self):
        self.assertEqual(interpret_measurement("waist", "in", None, None)["status"], INCONCLUSIVE)


class BuildInsightsTests(SimpleTestCase):
    def test_generated_from_rows_ordered_by_attention(self):
        rows = [
            {"label": "Waist", "status": IMPROVING, "status_label": "Improving", "overall_text": "Down 6.2 in"},
            {"label": "Lean Mass", "status": RECOVERING, "status_label": "Recovering", "overall_text": "Down 12 lb"},
            {"label": "Arm", "status": NEEDS_ATTENTION, "status_label": "Needs attention", "overall_text": "Down 1 in"},
        ]
        out = build_insights(rows)
        self.assertTrue(out[0].startswith("Arm: Needs attention"))
        self.assertTrue(out[1].startswith("Lean Mass: Recovering"))
