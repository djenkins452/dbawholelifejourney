# ==============================================================================
# File: apps/ai/tests/test_reasoning.py
# Description: Layer 2 reusable reasoning engines (apps/ai/chatgpt_cos/reasoning.py).
#   Reason OVER Layer 1 truth; never create truth. Confidence (weakest-link), risk
#   (read-only from interpretation), priority ranking, and transparency.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning.engines import (
    reasoning_confidence, confidence_rank, assess_risk, prioritize, explain,
)


class ReasoningConfidenceTests(SimpleTestCase):
    def test_weakest_link_wins(self):
        self.assertEqual(reasoning_confidence("high", "low"), "low")
        self.assertEqual(reasoning_confidence("high", "high", "medium"), "medium")

    def test_unknown_inputs_ignored(self):
        self.assertEqual(reasoning_confidence("high", None, ""), "high")

    def test_no_signals_defaults_medium(self):
        self.assertEqual(reasoning_confidence(), "medium")
        self.assertEqual(reasoning_confidence("garbage"), "medium")

    def test_rank_is_ordered(self):
        self.assertLess(confidence_rank("low"), confidence_rank("high"))


class RiskEngineTests(SimpleTestCase):
    def test_elevated_from_clinical_interpretation(self):
        fact = {"value": 240, "interpretation": {"concern": True, "display": "High",
                                                 "advice": "Recheck and hydrate."}}
        r = assess_risk(fact)
        self.assertEqual(r["level"], "elevated")
        self.assertEqual(r["advice"], "Recheck and hydrate.")

    def test_uncertain_from_temporal_warning(self):
        self.assertEqual(assess_risk({"value": 9, "temporal_warning": "future ts"})["level"],
                         "uncertain")

    def test_normal_when_no_interpretation(self):
        self.assertEqual(assess_risk({"value": 95})["level"], "normal")

    def test_never_invents_risk_from_a_bare_value(self):
        # No interpretation on the fact → Layer 2 must not manufacture a verdict.
        self.assertEqual(assess_risk({"value": 400})["level"], "normal")


class PriorityEngineTests(SimpleTestCase):
    def test_ranks_by_significance_descending(self):
        items = [{"n": "a", "s": 1}, {"n": "b", "s": 9}, {"n": "c", "s": 5}]
        ranked = prioritize(items, lambda it: it["s"])
        self.assertEqual([it["n"] for it in ranked], ["b", "c", "a"])


class TransparencyTests(SimpleTestCase):
    def test_attaches_the_basis(self):
        self.assertEqual(explain("That's high", "It's above your range"),
                         "That's high — it's above your range.")

    def test_no_basis_returns_conclusion(self):
        self.assertEqual(explain("That's high", ""), "That's high")
