"""
Deterministic tests for Body Intelligence measurement interpretation.

Pins the two guarantees:
  1. `infer_body_direction` classifies the BODY's trajectory from the composition picture
     (the user's Scenarios A–D), never a limb in isolation, and SAYS its confidence.
  2. `interpret_measurement` maps each measurement to Improving / Needs attention /
     No change with a LITERAL arrow, using the fixed direction for direct measures and the
     inferred body direction for limbs.
"""
from django.test import SimpleTestCase

from apps.health.services.measurement_interpretation import (
    IMPROVING, NEEDS_ATTENTION, NO_CHANGE,
    infer_body_direction, interpret_measurement,
)


class InferBodyDirectionTests(SimpleTestCase):
    def test_scenario_a_recomposition_is_improving(self):
        # Waist↓, fat↓, lean↑, (recomp flag) → losing fat, building muscle.
        bd = infer_body_direction({
            "fat_mass_delta_14d": -2.0, "lean_mass_delta_14d": 1.5,
            "recomposition_flag_14d": True,
        })
        self.assertEqual(bd["status"], IMPROVING)
        self.assertEqual(bd["confidence"], "high")
        self.assertEqual(bd["verdict"], "recomposition")

    def test_scenario_b_fat_loss_preserving_muscle_is_improving(self):
        # Fat↓, lean stable, muscle preserved → a smaller limb is fat loss.
        bd = infer_body_direction({
            "fat_mass_delta_14d": -1.5, "lean_mass_delta_14d": 0.1,
            "muscle_preservation_status": "good",
        })
        self.assertEqual(bd["status"], IMPROVING)
        self.assertEqual(bd["verdict"], "fat_loss_preserving")

    def test_scenario_c_muscle_loss_needs_attention(self):
        # Rapid loss, lean↓, high muscle-loss risk → likely losing muscle.
        bd = infer_body_direction({
            "fat_mass_delta_14d": -0.4, "lean_mass_delta_14d": -1.8,
            "muscle_loss_risk_level": "high", "weight_delta_14d": -6.0,
        })
        self.assertEqual(bd["status"], NEEDS_ATTENTION)
        self.assertEqual(bd["confidence"], "high")
        self.assertEqual(bd["verdict"], "muscle_loss")

    def test_scenario_d_conflicting_is_neutral_low_confidence(self):
        # Fat↑ and lean↑ together → not enough to judge a limb.
        bd = infer_body_direction({
            "fat_mass_delta_14d": 1.2, "lean_mass_delta_14d": 1.0,
        })
        self.assertEqual(bd["status"], NO_CHANGE)
        self.assertEqual(bd["confidence"], "low")

    def test_missing_data_is_neutral_low_confidence(self):
        self.assertEqual(infer_body_direction(None)["status"], NO_CHANGE)
        self.assertEqual(infer_body_direction({})["confidence"], "low")


class InterpretMeasurementTests(SimpleTestCase):
    IMPROVING_BD = {"status": IMPROVING, "confidence": "high", "summary": "recomp"}
    ATTENTION_BD = {"status": NEEDS_ATTENTION, "confidence": "high", "summary": "muscle loss"}
    LOWCONF_BD = {"status": NO_CHANGE, "confidence": "low", "summary": "unclear"}
    MEDIUM_BD = {"status": IMPROVING, "confidence": "medium", "summary": "likely fat loss"}

    def test_direct_decrease_good_toward_goal_is_improving(self):
        r = interpret_measurement("waist", -0.5, "in", None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "down")
        self.assertEqual(r["confidence"], "high")

    def test_direct_decrease_good_wrong_way_needs_attention(self):
        r = interpret_measurement("waist", 0.5, "in", None)
        self.assertEqual(r["status"], NEEDS_ATTENTION)
        self.assertEqual(r["arrow"], "up")

    def test_direct_increase_good_is_improving(self):
        r = interpret_measurement("lean_mass", 1.5, "lb", None)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "up")

    def test_neutral_metric_is_no_change_with_literal_arrow(self):
        r = interpret_measurement("chest", -1.0, "in", None)
        self.assertEqual(r["status"], NO_CHANGE)
        self.assertEqual(r["arrow"], "down")          # arrow is literal
        self.assertEqual(r["status_label"], "No goal")

    def test_near_zero_is_no_change(self):
        r = interpret_measurement("bmi", 0.0, "", None)
        self.assertEqual(r["status"], NO_CHANGE)
        self.assertEqual(r["arrow"], "flat")
        self.assertEqual(r["status_label"], "No change")

    def test_limb_up_during_recomposition_is_improving(self):
        # Scenario A: arm grows while recomposing → improving (muscle gain).
        r = interpret_measurement("arm_left", 0.25, "in", self.IMPROVING_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "up")

    def test_limb_down_during_fat_loss_is_improving(self):
        # Scenario B: a smaller limb while losing fat → improving (fat loss).
        r = interpret_measurement("thigh_left", -0.38, "in", self.IMPROVING_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["arrow"], "down")          # DOWN arrow, but GREEN

    def test_limb_down_during_muscle_loss_needs_attention(self):
        # Scenario C: a smaller limb while losing muscle → needs attention.
        r = interpret_measurement("arm_left", -0.3, "in", self.ATTENTION_BD)
        self.assertEqual(r["status"], NEEDS_ATTENTION)

    def test_limb_low_confidence_is_not_enough_evidence(self):
        # Scenario D: signals conflict → don't assert; say so.
        r = interpret_measurement("forearm_left", 0.25, "in", self.LOWCONF_BD)
        self.assertEqual(r["status"], NO_CHANGE)
        self.assertEqual(r["status_label"], "Not enough evidence")
        self.assertEqual(r["confidence"], "low")

    def test_limb_medium_confidence_is_hedged(self):
        r = interpret_measurement("calf_left", 0.2, "in", self.MEDIUM_BD)
        self.assertEqual(r["status"], IMPROVING)
        self.assertEqual(r["status_label"], "Likely improving")

    def test_unknown_metric_defaults_to_neutral(self):
        r = interpret_measurement("something_new", 2.0, "in", None)
        self.assertEqual(r["status"], NO_CHANGE)
        self.assertEqual(r["status_label"], "No goal")
