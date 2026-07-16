"""
Deterministic tests for Body Intelligence measurement interpretation.

Pins the guarantees:
  1. `infer_body_direction` classifies the BODY's trajectory from the composition picture
     (Scenarios A–D), never a limb in isolation, carries the EVIDENCE it used, and SAYS its
     confidence.
  2. `interpret_measurement` maps each measurement to Improving / Needs attention /
     Inconclusive with a LITERAL arrow — fixed direction for direct measures, inferred body
     direction for limbs — and never says "no change" when the truth is "can't tell yet".
"""
from django.test import SimpleTestCase

from apps.health.services.measurement_interpretation import (
    IMPROVING, NEEDS_ATTENTION, INCONCLUSIVE,
    infer_body_direction, interpret_measurement,
)


class InferBodyDirectionTests(SimpleTestCase):
    def test_scenario_a_recomposition_is_improving_with_evidence(self):
        bd = infer_body_direction({
            "fat_mass_delta_14d": -2.0, "lean_mass_delta_14d": 1.5,
            "recomposition_flag_14d": True,
        })
        self.assertEqual(bd["status"], IMPROVING)
        self.assertEqual(bd["confidence"], "high")
        self.assertEqual(bd["verdict"], "recomposition")
        self.assertIn("Body fat ↓", bd["evidence"])
        self.assertIn("Lean mass ↑", bd["evidence"])

    def test_scenario_b_fat_loss_preserving_muscle_is_improving(self):
        bd = infer_body_direction({
            "fat_mass_delta_14d": -1.5, "lean_mass_delta_14d": 0.1,
            "muscle_preservation_status": "good",
        })
        self.assertEqual(bd["status"], IMPROVING)
        self.assertEqual(bd["verdict"], "fat_loss_preserving")

    def test_scenario_c_muscle_loss_needs_attention(self):
        bd = infer_body_direction({
            "fat_mass_delta_14d": -0.4, "lean_mass_delta_14d": -1.8,
            "muscle_loss_risk_level": "high", "weight_delta_14d": -6.0,
        })
        self.assertEqual(bd["status"], NEEDS_ATTENTION)
        self.assertEqual(bd["confidence"], "high")
        self.assertIn("Lean mass ↓", bd["evidence"])
        self.assertEqual(bd["summary"], "Possible muscle loss.")

    def test_scenario_d_conflicting_is_inconclusive_low_confidence(self):
        bd = infer_body_direction({"fat_mass_delta_14d": 1.2, "lean_mass_delta_14d": 1.0})
        self.assertEqual(bd["status"], INCONCLUSIVE)
        self.assertEqual(bd["confidence"], "low")

    def test_missing_data_is_inconclusive_low_confidence(self):
        self.assertEqual(infer_body_direction(None)["status"], INCONCLUSIVE)
        self.assertEqual(infer_body_direction({})["confidence"], "low")


class InterpretMeasurementTests(SimpleTestCase):
    IMPROVING_BD = {"status": IMPROVING, "confidence": "high",
                    "evidence": ["Body fat ↓", "Lean mass ↑"], "summary": "Likely muscle gain while losing fat."}
    ATTENTION_BD = {"status": NEEDS_ATTENTION, "confidence": "high",
                    "evidence": ["Lean mass ↓"], "summary": "Possible muscle loss."}
    LOWCONF_BD = {"status": INCONCLUSIVE, "confidence": "low", "evidence": [], "summary": "unclear"}
    MEDIUM_BD = {"status": IMPROVING, "confidence": "medium",
                 "evidence": ["Body fat ↓"], "summary": "likely fat loss"}

    def test_direct_decrease_good_toward_goal_is_improving(self):
        r = interpret_measurement("waist", -0.5, "in", None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "down")
        self.assertTrue(r["reason"])

    def test_direct_decrease_good_wrong_way_needs_attention(self):
        r = interpret_measurement("waist", 0.5, "in", None)
        self.assertEqual(r["status"], NEEDS_ATTENTION)
        self.assertEqual(r["arrow"], "up")

    def test_direct_increase_good_is_improving(self):
        r = interpret_measurement("lean_mass", 1.5, "lb", None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "up")

    def test_neutral_metric_is_inconclusive_with_literal_arrow(self):
        r = interpret_measurement("chest", -1.0, "in", None)
        self.assertEqual(r["status"], INCONCLUSIVE)
        self.assertEqual(r["status_label"], "Inconclusive")
        self.assertEqual(r["arrow"], "down")          # arrow is literal
        self.assertIn("no established healthy direction", r["reason"].lower())

    def test_near_zero_is_inconclusive_not_a_false_no_change(self):
        r = interpret_measurement("bmi", 0.0, "", None)
        self.assertEqual(r["status"], INCONCLUSIVE)
        self.assertEqual(r["arrow"], "flat")
        self.assertEqual(r["status_label"], "Inconclusive")

    def test_limb_up_during_recomposition_is_improving_with_evidence(self):
        r = interpret_measurement("arm_left", 0.25, "in", self.IMPROVING_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "up")
        self.assertEqual(r["evidence"], ["Body fat ↓", "Lean mass ↑"])

    def test_limb_down_during_fat_loss_is_improving(self):
        # A smaller limb while losing fat → improving (DOWN arrow, but GREEN).
        r = interpret_measurement("thigh_left", -0.38, "in", self.IMPROVING_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "down")

    def test_limb_down_during_muscle_loss_needs_attention(self):
        r = interpret_measurement("arm_left", -0.3, "in", self.ATTENTION_BD)
        self.assertEqual(r["status"], NEEDS_ATTENTION)
        self.assertEqual(r["evidence"], ["Lean mass ↓"])

    def test_limb_low_confidence_is_inconclusive_not_no_change(self):
        r = interpret_measurement("forearm_left", 0.25, "in", self.LOWCONF_BD)
        self.assertEqual(r["status"], INCONCLUSIVE)
        self.assertEqual(r["status_label"], "Inconclusive")
        self.assertEqual(r["confidence"], "low")

    def test_limb_medium_confidence_is_hedged(self):
        r = interpret_measurement("calf_left", 0.2, "in", self.MEDIUM_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["status_label"], "Likely improving")

    def test_unknown_metric_defaults_to_inconclusive(self):
        r = interpret_measurement("something_new", 2.0, "in", None)
        self.assertEqual(r["status"], INCONCLUSIVE)
        self.assertEqual(r["status_label"], "Inconclusive")
