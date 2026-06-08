"""Phase 0 — shadow classifier accuracy + behavior tests.

These are PURE tests (no DB, no Django models). They prove the instrument hits
the >=85% golden-corpus mode-accuracy gate BEFORE any live-path wiring.
"""

from django.test import SimpleTestCase

from apps.ai.cognitive_mode import golden_corpus as gc
from apps.ai.cognitive_mode.shadow_classifier import classify
from apps.ai.cognitive_mode.taxonomy import Mode


class ShadowClassifierGoldenTests(SimpleTestCase):
    def test_mode_accuracy_meets_threshold(self):
        total = len(gc.GOLDEN)
        correct = 0
        misses = []
        for entry in gc.GOLDEN:
            pred = classify(entry["message"])
            if gc.mode_is_correct(entry, pred.mode):
                correct += 1
            else:
                misses.append((entry["id"], entry["expected_mode"], pred.mode))
        acc = correct / total
        self.assertGreaterEqual(
            acc, 0.85,
            msg=f"Mode accuracy {acc:.0%} below 85% gate. Misses: {misses}",
        )

    def test_coach_tail_detected_when_expected(self):
        for entry in gc.GOLDEN:
            if entry.get("coach_tail_expected"):
                pred = classify(entry["message"])
                # coach_tail only meaningful on analyze predictions
                if pred.mode in (Mode.ANALYZE, Mode.ANALYZE_COACH):
                    self.assertTrue(
                        pred.coach_tail,
                        msg=f"{entry['id']}: expected coach_tail=True, got False",
                    )

    def test_clean_retrieve_does_not_escalate_to_analyze(self):
        # "What is my current weight?" must stay Retrieve.
        pred = classify("What is my current weight?")
        self.assertEqual(pred.mode, Mode.RETRIEVE)

    def test_strong_analyze_beats_domain_lookup(self):
        # Domain token present (weight) but judgment verb -> analyze, not retrieve.
        pred = classify("What do you think about my weight history?")
        self.assertEqual(pred.mode, Mode.ANALYZE)

    def test_protein_today_is_retrieve_not_analyze(self):
        # The 'how am I doing' + metric + today discrimination.
        pred = classify("How am I doing on protein today?")
        self.assertEqual(pred.mode, Mode.RETRIEVE)

    def test_overall_is_analyze_not_retrieve(self):
        pred = classify("How am I doing overall?")
        self.assertEqual(pred.mode, Mode.ANALYZE)

    def test_reflect_inner_state(self):
        self.assertEqual(classify("I feel off lately.").mode, Mode.REFLECT)

    def test_execute_next_action(self):
        self.assertEqual(classify("What should I do next?").mode, Mode.EXECUTE)

    def test_provenance_is_retrieve(self):
        self.assertEqual(classify("Where is Perfect Amino coming from?").mode, Mode.RETRIEVE)

    def test_empty_message_is_unknown(self):
        self.assertEqual(classify("").mode, Mode.UNKNOWN)

    def test_prediction_carries_reason_and_package(self):
        pred = classify("What do you think about my weight history?")
        self.assertTrue(pred.reason)
        # Analyze:weight should request the multi-signal package.
        self.assertIn("weight_velocity", pred.package_needed)
        self.assertIn("med_changes_in_window", pred.package_needed)

    def test_classifier_is_pure_and_stable(self):
        msg = "What do you think about my weight history?"
        a = classify(msg)
        b = classify(msg)
        self.assertEqual(a.mode, b.mode)
        self.assertEqual(a.domain, b.domain)
        self.assertEqual(a.confidence, b.confidence)
