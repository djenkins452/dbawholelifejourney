# ==============================================================================
# File: apps/health/tests/test_glucose_interpretation.py
# Description: RELEASE-BLOCKER regression — clinical Interpretation layer. A 43 mg/dL
#   glucose reading (severe hypoglycemia) must NEVER be narrated as "good/healthy/in
#   range". Truth → Interpretation → Narration. Origin: real Beth conversation.
# ==============================================================================
from django.test import SimpleTestCase

from apps.health.services.glucose_interpretation import (
    classify_glucose_mg_dl, interpret, to_mg_dl,
)
from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence

_REASSURING = ("good", "healthy", "in range", "fine", "normal", "excellent")


class GlucoseBandTests(SimpleTestCase):
    def test_severe_low_is_danger(self):
        gi = classify_glucose_mg_dl(43)
        self.assertEqual(gi["band"], "very_low")
        self.assertEqual(gi["safety"], "danger")
        self.assertTrue(gi["concern"])
        self.assertIn("dangerously low", gi["advice"].lower())

    def test_bands(self):
        self.assertEqual(classify_glucose_mg_dl(60)["band"], "low")
        self.assertEqual(classify_glucose_mg_dl(110)["band"], "normal")
        self.assertEqual(classify_glucose_mg_dl(200)["band"], "high")
        self.assertEqual(classify_glucose_mg_dl(300)["band"], "very_high")

    def test_mmol_conversion(self):
        self.assertAlmostEqual(to_mg_dl(2.4, "mmol/L"), 43.2, places=1)
        self.assertEqual(interpret(2.4, "mmol/L")["safety"], "danger")  # 2.4 mmol/L ≈ 43


class GlucoseNarrationSafetyTests(SimpleTestCase):
    def test_43_never_narrated_as_good(self):
        fact = {"value": 43, "unit": "mg/dL", "interpretation": classify_glucose_mg_dl(43)}
        s = format_fact_sentence("last_glucose_reading", fact).lower()
        self.assertIn("very low", s)
        self.assertIn("verify", s)               # surfaces verification, never reassures
        for word in _REASSURING:
            self.assertNotIn(word, s)            # no reassurance whatsoever

    def test_normal_value_states_in_range_without_advice(self):
        fact = {"value": 110, "unit": "mg/dL", "interpretation": classify_glucose_mg_dl(110)}
        s = format_fact_sentence("last_glucose_reading", fact)
        self.assertIn("In Range", s)
        self.assertNotIn("verify", s.lower())    # no alarm for a normal value


class GlucoseModelDelegationTests(SimpleTestCase):
    def test_model_property_delegates_to_canonical_bands(self):
        # GlucoseEntry.glucose_status must agree with the canonical interpreter (single
        # source). Tested without DB via a lightweight stand-in.
        from apps.health.models import GlucoseEntry
        e = GlucoseEntry(value=43, unit="mg/dL")
        self.assertEqual(e.glucose_status, "very_low")
        self.assertEqual(e.glucose_status_display, "Very Low")
