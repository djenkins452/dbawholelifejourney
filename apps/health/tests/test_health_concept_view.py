# ==============================================================================
# File: apps/health/tests/test_health_concept_view.py
# Description: The health concept view exposes deterministic FACTS grouped by concept and
#   EXCLUDES WLJ's own reasoning (scorecard, verdict, status, narrative, advice). This is the
#   boundary the whole "concept" milestone rests on: WLJ organizes; the model judges.
# ==============================================================================
from django.test import SimpleTestCase

from apps.health.services.health_concept_view import build_health_concept_view

# A realistic slice of the health SAE state, mixing facts with WLJ's reasoning (as prod does).
_STATE = {
    "weight_current": 282.9, "weight_change_30d": -2.8,
    "body_fat_current": 35.6, "bmi_current": 36.3, "waist_current": 54.72,
    "body_composition": {
        "latest": {"fat_mass": 100.71, "lean_mass": 182.2},
        "delta": {"fat_mass": -6.48, "lean_mass": 8.8, "body_fat_pct": -2.6, "waist": 1.22,
                  "bmi": 0.3},
        "previous_date": "2026-07-03", "latest_date": "2026-08-02",
        # reasoning that MUST NOT leak:
        "trend_summary": ["Lean Mass trending up (improving)"],
        "largest_improvement": {"metric": "lean_mass", "delta": 8.8},
    },
    "glucose_avg_7d": 114, "glucose_avg_30d": 114, "time_in_range_pct_30d": 94.7,
    "projected_a1c": 6.3,
    "bp_reading": "138/87", "heart_rate_avg_7d": 69,
    "sleep_avg_hours_7d": 5.7, "latest_hrv": 19.1,
    "steps_avg_7d": 3339, "water_avg_oz_7d": 61.2, "blood_oxygen_avg_7d": 95.6,
    # WLJ REASONING that must be excluded entirely:
    "health_score": 60,
    "health_score_drivers": {"domains": {"sleep": {"score": 66}}, "primary_risk": "workout",
                             "immediate_focus": "Increase workout frequency"},
    "physical_decision": {"verdict": "recomposition",
                          "recommended_action": "Add 30-40g protein at your next meal.",
                          "narrative": "Your body is responding right now..."},
    "fat_loss_phase": "RECOMPOSITION", "weight_status": "good",
    "muscle_loss_risk_level": "MED", "plateau_status": "RECOMP",
}


class HealthConceptViewTests(SimpleTestCase):
    def setUp(self):
        self.concepts = build_health_concept_view(_STATE)["concepts"]

    def test_facts_are_grouped_into_concepts(self):
        self.assertIn("body_composition", self.concepts)
        self.assertIn("glucose", self.concepts)
        self.assertIn("cardiovascular", self.concepts)
        self.assertIn("sleep_recovery", self.concepts)

    def test_recomposition_components_arrive_as_one_object(self):
        # weight + fat mass + lean mass under ONE concept, so the relationship is perceptible.
        members = self.concepts["body_composition"]["members"]
        self.assertEqual(members["weight"]["value"], 282.9)
        self.assertEqual(members["fat_mass"]["change"], -6.48)   # fat down
        self.assertEqual(members["lean_mass"]["change"], 8.8)    # lean up
        self.assertEqual(members["body_fat_pct"]["change"], -2.6)

    def test_wlj_reasoning_is_completely_excluded(self):
        # The verdict, scorecard, narrative, advice, status, risk labels must NOT appear.
        import json
        blob = json.dumps(self.concepts).lower()
        for leaked in ("recomposition", "health_score", "primary_risk", "immediate_focus",
                       "recommended_action", "narrative", "verdict", "improving",
                       "largest_improvement", "muscle_loss", "plateau", "add 30-40g",
                       "increase workout", '"good"', "phase"):
            self.assertNotIn(leaked, blob, f"WLJ reasoning leaked into the facts: {leaked!r}")

    def test_never_coerces_a_label_into_a_number(self):
        # Only numeric facts (and the bp reading string) become members; a status word never
        # sneaks in as a value.
        for c in self.concepts.values():
            for m in c["members"].values():
                v = m["value"]
                self.assertTrue(isinstance(v, (int, float)) or v == "138/87")

    def test_empty_or_bad_state_is_safe(self):
        self.assertEqual(build_health_concept_view({}), {"concepts": {}})
        self.assertEqual(build_health_concept_view(None), {"concepts": {}})
