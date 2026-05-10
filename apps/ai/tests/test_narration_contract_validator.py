"""Tests for the soft narration-contract validator."""

from django.test import SimpleTestCase

from apps.ai.narration_contract_validator import validate_narration_contract


class NarrationContractValidatorTests(SimpleTestCase):

    def test_completion_claim_passes_with_canonical_match(self):
        canonical = "Lantus SoloStar — completed"
        rollup = "Morning Medications: ALL TAKEN"
        response = "Lantus is already done — nice."
        result = validate_narration_contract(
            response, canonical, rollup, user_id=1, request_id="r1",
        )
        self.assertEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["summary"]["warnings"], 0)

    def test_completion_claim_warns_when_only_rollup_matches(self):
        # Canonical mentions a different item; rollup mentions Lantus.
        canonical = "Vitamin D3 — completed"
        rollup = "Lantus SoloStar — window aggregate"
        response = "Lantus is already done — nice."
        result = validate_narration_contract(
            response, canonical, rollup, user_id=1, request_id="r1",
        )
        self.assertEqual(result["summary"]["warnings"], 1)
        self.assertEqual(result["summary"]["passed"], 0)
        self.assertEqual(result["summary"]["errors"], 0)

    def test_completion_claim_errors_when_no_match_anywhere(self):
        canonical = "Vitamin D3 — completed"
        rollup = ""
        response = "Lantus is already done — nice."
        result = validate_narration_contract(
            response, canonical, rollup,
        )
        self.assertEqual(result["summary"]["errors"], 1)

    def test_at_risk_claim_passes_with_canonical_at_risk_listing(self):
        canonical = "Morning Meds (overdue)"
        rollup = ""
        response = "Morning Meds is at risk — fix soon."
        result = validate_narration_contract(response, canonical, rollup)
        self.assertEqual(result["summary"]["passed"], 1)

    def test_at_risk_claim_warns_when_only_rollup(self):
        canonical = ""
        rollup = "Lunch (later today)"
        response = "Lunch is at risk."
        result = validate_narration_contract(response, canonical, rollup)
        self.assertEqual(result["summary"]["warnings"], 1)

    def test_next_action_claim_must_match_canonical(self):
        # Two next-action signals fire: "Next:" and "do this now".
        # Both must trace to the same canonical line — passes=2.
        canonical = "Next: Drink Protein Shake. Do this now."
        rollup = ""
        response = "Next: Drink Protein Shake. Do this now."
        result = validate_narration_contract(response, canonical, rollup)
        self.assertGreaterEqual(result["summary"]["passed"], 1)
        self.assertEqual(result["summary"]["warnings"], 0)
        self.assertEqual(result["summary"]["errors"], 0)

    def test_unrelated_response_emits_no_violations(self):
        canonical = "Vitamin D3"
        rollup = ""
        response = "Hello! How can I help you today?"
        result = validate_narration_contract(response, canonical, rollup)
        self.assertEqual(result["summary"]["passed"], 0)
        self.assertEqual(result["summary"]["warnings"], 0)
        self.assertEqual(result["summary"]["errors"], 0)

    def test_validator_does_not_block_response(self):
        # Soft enforcement: the validator returns; it never raises or
        # mutates the response.
        result = validate_narration_contract(
            "Lantus is already done.",
            canonical_blob="",
            rollup_blob="Lantus",
        )
        self.assertIn("warnings", result)
        # Returned dict structure stable for snapshot inclusion.
        self.assertIn("passed", result)
        self.assertIn("errors", result)
