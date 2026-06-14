"""Regression: weight-delta hallucination guard.

Trust bug: Beth said "Over the last 14 days, your weight decreased by about
286.2 lbs" — the CURRENT weight (286.2) stated as the 14-day delta (which was
actually -1.2 lbs). Root cause: the trend-breakdown is LLM-narrated and the
context supplies only the current weight + a trend word (no labeled delta), so
the LLM substituted the current weight as the change. The retry was correct
purely by LLM sampling — hence "first wrong, second right".

Fix: a deterministic fail-closed guard (`correct_implausible_weight_delta`)
inside the locked-facts truth validator, which runs on BOTH the streaming and
non-streaming response paths. These tests lock the guard's behavior.
"""

from django.test import TestCase

from apps.ai.cognitive_mode.health_truth import (
    _SAFE_DELTA_FALLBACK,
    correct_implausible_weight_delta,
)
from apps.ai.cos_truth_validator import validate_locked_facts
from apps.users.models import User


class WeightDeltaGuardFunctionTests(TestCase):
    """Pure-function behavior of the deterministic delta guard."""

    # ── Test 1 — Normal trend passes untouched ────────────────────────────
    def test_normal_trend_is_not_altered(self):
        text = ("Your weight trend over the last 14 days shows a decrease of "
                "1.2 lbs, bringing you to 286.2 lbs.")
        out, flagged = correct_implausible_weight_delta(text, current_weight=286.2)
        self.assertEqual(flagged, 0)
        self.assertEqual(out, text)
        # The valid delta (1.2) survives; no "286.2 lbs decrease" artifact.
        self.assertIn("1.2", out)
        self.assertNotIn(_SAFE_DELTA_FALLBACK, out)

    def test_plain_down_small_delta_not_altered(self):
        text = "Over the last 14 days your weight is down 1.2 lbs."
        out, flagged = correct_implausible_weight_delta(text, current_weight=286.2)
        self.assertEqual(flagged, 0)
        self.assertEqual(out, text)

    # ── The exact production hallucination ────────────────────────────────
    def test_current_weight_stated_as_delta_fails_closed(self):
        text = ("Over the last 14 days, your weight decreased by about 286.2 "
                "lbs. Your weight trend is heading in the right direction.")
        out, flagged = correct_implausible_weight_delta(text, current_weight=286.2)
        self.assertGreaterEqual(flagged, 1)
        self.assertIn(_SAFE_DELTA_FALLBACK, out)
        # The absurd number is gone; the benign trailing sentence is kept.
        self.assertNotIn("286.2 lbs", out)
        self.assertIn("right direction", out)

    # ── Test 2 — Missing prior must never substitute current as delta ─────
    def test_missing_prior_substitution_is_caught(self):
        # Even with no current weight known, the >bound short-window rule fires.
        text = "Over the last 14 days your weight is down 286.2 lbs."
        out, flagged = correct_implausible_weight_delta(text, current_weight=None)
        self.assertEqual(flagged, 1)
        self.assertIn(_SAFE_DELTA_FALLBACK, out)
        self.assertNotIn("286.2", out)

    # ── Test 3 — Implausible delta fails closed ───────────────────────────
    def test_implausible_large_short_window_delta(self):
        text = "Your weight dropped 45 lbs in the last 14 days."
        out, flagged = correct_implausible_weight_delta(text, current_weight=286.2)
        self.assertEqual(flagged, 1)
        self.assertIn(_SAFE_DELTA_FALLBACK, out)

    # ── Precision: legitimate statements are NOT clobbered ────────────────
    def test_long_haul_loss_not_flagged(self):
        # No short-window marker → the >20 rule does not apply.
        text = "You've lost 40 lbs of weight since last year — great consistency."
        out, flagged = correct_implausible_weight_delta(text, current_weight=246.0)
        self.assertEqual(flagged, 0)
        self.assertEqual(out, text)

    def test_non_weight_number_not_flagged(self):
        # A 45 lb change with no weight context (e.g. a lift) must be ignored.
        text = "Your squat went up 45 lbs this week — strong progress."
        out, flagged = correct_implausible_weight_delta(text, current_weight=286.2)
        self.assertEqual(flagged, 0)
        self.assertEqual(out, text)

    def test_guard_never_raises_on_empty(self):
        self.assertEqual(correct_implausible_weight_delta("", 286.2), ("", 0))
        self.assertEqual(correct_implausible_weight_delta(None, 286.2), (None, 0))


class WeightDeltaGuardValidatorParityTests(TestCase):
    """Test 4 — the guard runs identically regardless of regenerate mode.

    Both the non-streaming (allow_regenerate=True) and streaming
    (allow_regenerate=False) callers route through validate_locked_facts, so
    the fail-closed behavior is deterministic across the first response and any
    retry — no "first wrong, second right".
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="weight-delta-guard@test.com", password="x" * 20,
        )
        self.locked = {
            '_raw': {'weight_current': 286.2, 'weight_unit': 'lb'},
            'overall_summary': '',
        }
        self.bad = ("Over the last 14 days, your weight decreased by about "
                    "286.2 lbs. Your weight trend is heading in the right "
                    "direction.")
        self.good = ("Your weight trend over the last 14 days shows a decrease "
                     "of 1.2 lbs, bringing you to 286.2 lbs.")

    def _assert_failed_closed(self, validated, violations):
        self.assertIn(_SAFE_DELTA_FALLBACK, validated)
        self.assertNotIn("286.2 lbs", validated)
        self.assertTrue(
            any(v.get('type') == 'implausible_weight_delta' for v in violations)
        )

    def test_non_streaming_path_fails_closed(self):
        validated, violations = validate_locked_facts(
            self.bad, self.locked, self.user, allow_regenerate=True,
        )
        self._assert_failed_closed(validated, violations)
        # Delta violation must not force regeneration (should_reject False).
        delta_v = [v for v in violations
                   if v.get('type') == 'implausible_weight_delta'][0]
        self.assertFalse(delta_v.get('should_reject'))

    def test_streaming_path_fails_closed(self):
        validated, violations = validate_locked_facts(
            self.bad, self.locked, self.user, allow_regenerate=False,
        )
        self._assert_failed_closed(validated, violations)

    def test_retry_parity_same_result_both_modes(self):
        v_stream, _ = validate_locked_facts(
            self.bad, self.locked, self.user, allow_regenerate=False,
        )
        v_nonstream, _ = validate_locked_facts(
            self.bad, self.locked, self.user, allow_regenerate=True,
        )
        self.assertEqual(v_stream, v_nonstream)

    def test_valid_response_passes_through_unchanged(self):
        validated, violations = validate_locked_facts(
            self.good, self.locked, self.user, allow_regenerate=True,
        )
        self.assertEqual(validated, self.good)
        self.assertFalse(
            any(v.get('type') == 'implausible_weight_delta' for v in violations)
        )
