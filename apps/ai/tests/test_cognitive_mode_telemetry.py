"""Phase 0 — telemetry + model_ab safety tests.

Proves the inert pieces are genuinely inert: telemetry never raises and never
persists; model A/B refuses to generate without approval.
"""

from django.test import SimpleTestCase

from apps.ai.cognitive_mode import model_ab
from apps.ai.cognitive_mode.telemetry import (
    ModeObservation,
    record_mode_observation,
    hash_message,
    extract_safe_features,
)


class TelemetryStubTests(SimpleTestCase):
    def test_record_returns_payload_and_never_raises(self):
        obs = ModeObservation(
            request_id="req-1",
            user_id=42,
            predicted_mode="analyze",
            predicted_domain="weight",
            mode_confidence=0.9,
            mode_reason="test",
        )
        payload = record_mode_observation(obs)
        self.assertEqual(payload["predicted_mode"], "analyze")
        self.assertEqual(payload["predicted_domain"], "weight")

    def test_record_swallows_bad_input(self):
        # Passing a non-observation must not raise (guaranteed no-op).
        result = record_mode_observation(object())  # type: ignore[arg-type]
        self.assertEqual(result, {})

    def test_hash_is_stable_and_opaque(self):
        h1 = hash_message("What is my weight?")
        h2 = hash_message("what is my weight?")  # normalized -> same hash
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        self.assertNotIn("weight", h1)  # opaque

    def test_safe_features_contain_no_free_text(self):
        feats = extract_safe_features("How much protein did I eat today?")
        self.assertIn("len_bucket", feats)
        self.assertTrue(feats["has_today"])
        # No raw message stored among features.
        self.assertNotIn("protein", str(feats).lower())

    def test_message_text_defaults_none(self):
        obs = ModeObservation(request_id="r")
        self.assertIsNone(obs.as_dict()["message_text"])


class ModelABSafetyTests(SimpleTestCase):
    def test_generate_candidate_blocked_without_approval(self):
        with self.assertRaises(model_ab.ModelABNotApproved):
            model_ab.generate_candidate("p", {}, "some-model", approved=False)

    def test_generate_candidate_blocked_even_if_approved_but_flag_off(self):
        # approved=True but flag off (default) -> still blocked.
        with self.assertRaises(model_ab.ModelABNotApproved):
            model_ab.generate_candidate("p", {}, "some-model", approved=True)

    def test_build_pair_does_not_generate(self):
        pair = model_ab.build_pair("ref-1", "hello", {"a": 1}, "candidate-x")
        self.assertEqual(pair.answer_a, "")
        self.assertEqual(pair.answer_b, "")
        self.assertEqual(pair.model_b, "candidate-x")
        self.assertTrue(pair.context_fingerprint)

    def test_score_answer_flags_generic_language(self):
        scores = model_ab.score_answer("Make sure to stay consistent.", {})
        self.assertIn("generic_language", scores["auto_flags"])
