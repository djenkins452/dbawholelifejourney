"""P1 weight-contradiction guard + diagnostic tests.

Proves: canonical=289.9, a draft saying 287.3 is corrected; a draft saying
289.9 passes untouched; goal/lift/historical weights are NOT clobbered; the
diagnostic never raises and logs no raw message text.
"""

from django.test import SimpleTestCase

from apps.ai.cognitive_mode import health_truth as ht


class WeightCorrectionTests(SimpleTestCase):
    CANON = 289.9

    def test_contradictory_current_weight_is_corrected(self):
        draft = "Your weight is currently at 287.3 lbs, which is good progress."
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertIn("289.9", out)
        self.assertNotIn("287.3", out)
        self.assertEqual(corr, [(287.3, 289.9)])

    def test_matching_current_weight_passes_untouched(self):
        draft = "You're at 289.9 lb — nice steady progress."
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertEqual(out, draft)
        self.assertEqual(corr, [])

    def test_within_tolerance_not_corrected(self):
        draft = "Your current weight is 289.9."  # canonical 290.0 within 1.0
        out, corr = ht.correct_weight_contradictions(draft, 290.0)
        self.assertEqual(corr, [])

    def test_multiple_phrasings_corrected(self):
        for draft in [
            "Your weight is currently at 287.3 lbs.",
            "Your current weight is 287.3.",
            "You're at 287.3 lbs.",
            "Currently weighing 287.3.",
            "current weight: 287.3",
        ]:
            out, corr = ht.correct_weight_contradictions(draft, self.CANON)
            self.assertIn("289.9", out, msg=f"failed to correct: {draft!r}")
            self.assertEqual(len(corr), 1, msg=f"draft={draft!r}")

    # ── precision: do NOT clobber non-current-weight numbers ──
    def test_goal_weight_preserved(self):
        draft = "You're at 289.9 lb and your goal is 250 lbs — 39.9 to go."
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertIn("250 lbs", out)  # goal untouched
        self.assertEqual(corr, [])

    def test_historical_trend_preserved(self):
        # canonical 289.9; a trend sentence mentions older values — must NOT touch
        draft = "Over 30 days you've gone from 295.0 to 289.9 lbs."
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertIn("295.0", out)
        self.assertIn("289.9", out)
        self.assertEqual(corr, [])

    def test_lifted_weight_preserved(self):
        draft = "Your current weight is 289.9. Nice squat at 225 lb today!"
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertIn("225 lb", out)
        self.assertEqual(corr, [])

    def test_implausible_number_ignored(self):
        # "currently at 12" is not a body weight — leave it
        draft = "You're currently at 12 lb of water intake logged."
        out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertEqual(corr, [])

    def test_none_canonical_is_noop(self):
        draft = "Your weight is currently at 287.3 lbs."
        out, corr = ht.correct_weight_contradictions(draft, None)
        self.assertEqual(out, draft)
        self.assertEqual(corr, [])

    def test_guard_disabled_is_noop(self):
        draft = "Your weight is currently at 287.3 lbs."
        with self.settings(WLJ_BETH_WEIGHT_GUARD_ENABLED=False):
            out, corr = ht.correct_weight_contradictions(draft, self.CANON)
        self.assertEqual(out, draft)
        self.assertEqual(corr, [])


class WeightDiagnosticTests(SimpleTestCase):
    def test_extract_weight_values(self):
        vals = ht.extract_all_weight_values("ctx: 289.9 lb ... 287.3 lbs ... 250 lb goal")
        self.assertIn(289.9, vals)
        self.assertIn(287.3, vals)
        self.assertIn(250.0, vals)

    def test_diagnostic_never_raises(self):
        class _U:
            id = 7
        # Should not raise even with odd inputs.
        ht.log_weight_diagnostic(_U(), "analyze_health_v0",
                                 "Am I losing weight too quickly?",
                                 "context has 289.9 lb", "draft says 287.3 lbs", 289.9)

    def test_message_hash_is_opaque(self):
        h = ht._hash_message("Am I losing weight too quickly?")
        self.assertEqual(len(h), 16)
        self.assertNotIn("weight", h)

    def test_diag_disabled_is_silent(self):
        class _U:
            id = 7
        with self.settings(WLJ_BETH_WEIGHT_DIAG_ENABLED=False):
            ht.log_weight_diagnostic(_U(), "r", "msg", "ctx", "draft", 289.9)


class CanonicalWeightLockTests(SimpleTestCase):
    def test_get_canonical_weight_handles_missing(self):
        class _U:
            id = 1
        # No SAE state for a bare mock user -> (None, None), never raises.
        val, unit = ht.get_canonical_weight(_U())
        self.assertIsNone(val)
