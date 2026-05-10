"""Tests for the Narration Contract preamble + section-header
machinery. Pure module — no DB, no fixtures."""

from django.test import SimpleTestCase

from apps.core.ai_orchestrator.narration_contract import (
    ALL_TIERS,
    TIER_ADVISORY,
    TIER_CANONICAL,
    TIER_CONTEXTUAL,
    TIER_ROLLUP,
    is_canonical_tier,
    is_rollup_tier,
    is_state_determining_tier,
    narration_contract_preamble,
    section_header,
)


class NarrationContractPreambleTests(SimpleTestCase):

    def test_preamble_lists_all_four_tiers(self):
        text = narration_contract_preamble()
        for tier in ALL_TIERS:
            self.assertIn(tier, text)

    def test_preamble_states_strict_rules(self):
        text = narration_contract_preamble()
        # Must explicitly forbid rollup-to-per-item conversion.
        self.assertIn("rollup", text.lower())
        self.assertIn("NEVER", text)
        # Must mention the five claim families.
        for kw in ("done", "overdue", "at risk", "next", "fix"):
            self.assertIn(kw.lower(), text.lower())

    def test_preamble_specifies_default_tier(self):
        text = narration_contract_preamble()
        self.assertIn("contextual", text.lower())
        self.assertIn("default", text.lower())


class SectionHeaderTests(SimpleTestCase):

    def test_canonical_header(self):
        h = section_header(TIER_CANONICAL, "DECISIONS")
        self.assertEqual(h, "[TIER:canonical_item_truth] DECISIONS")

    def test_rollup_header(self):
        h = section_header(TIER_ROLLUP, "DAILY EXECUTION STATUS")
        self.assertTrue(h.startswith("[TIER:rollup_summary] "))

    def test_advisory_header(self):
        h = section_header(TIER_ADVISORY, "ROUTINE MAINTENANCE PLAN")
        self.assertTrue(h.startswith("[TIER:advisory] "))

    def test_contextual_header(self):
        h = section_header(TIER_CONTEXTUAL, "FORWARD SCHEDULE")
        self.assertTrue(h.startswith("[TIER:contextual] "))

    def test_invalid_tier_marked_invalid(self):
        h = section_header("nope", "X")
        self.assertIn("INVALID:", h)


class TierClassifiersTests(SimpleTestCase):

    def test_canonical_is_state_determining(self):
        self.assertTrue(is_state_determining_tier(TIER_CANONICAL))
        self.assertTrue(is_canonical_tier(TIER_CANONICAL))

    def test_rollup_is_not_state_determining(self):
        self.assertFalse(is_state_determining_tier(TIER_ROLLUP))
        self.assertTrue(is_rollup_tier(TIER_ROLLUP))

    def test_advisory_and_contextual_not_state_determining(self):
        self.assertFalse(is_state_determining_tier(TIER_ADVISORY))
        self.assertFalse(is_state_determining_tier(TIER_CONTEXTUAL))
