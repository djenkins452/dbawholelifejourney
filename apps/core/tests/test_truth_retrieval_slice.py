"""
Truth Retrieval Certification — deterministic (Owner-1) slice.

Executes EVERY QuestionSpec in the first vertical slice (Weight · Medication ·
Nutrition) against its provider surface + deterministic fixture, with NO OpenAI.
A green run means: for each certified capability, WLJ's canonical provider returns
the right value — so when Customer Truth (Owner-2) runs the same NL questions live,
a failure represents a genuine product defect, not missing deterministic coverage.
"""
from django.test import TestCase

from apps.core.truth.certification_fixtures import FIXTURES
from apps.core.truth.question_specs import (
    CAPABILITIES, SLICE_SPECS, capability_matrix, matrix_summary, run_spec,
)


class TruthRetrievalSliceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Build each deterministic fixture once (returns (user, anchors)).
        cls.built = {name: fn() for name, fn in FIXTURES.items()}

    def test_every_slice_spec_certifies_deterministically(self):
        failures = []
        for spec in SLICE_SPECS:
            user, anchors = self.built[spec.fixture]
            passed, detail = run_spec(user, spec, anchors)
            if not passed:
                failures.append((spec.id, spec.capability, detail))
        self.assertEqual(failures, [], f"deterministic cert failures: {failures}")

    def test_slice_covers_the_expected_capabilities(self):
        caps = {s.capability for s in SLICE_SPECS}
        # the slice exercises current/historical/latest/timeline/list/existence/comparison
        for expected in ("current_fact", "historical", "latest", "timeline",
                         "list", "existence", "comparison"):
            self.assertIn(expected, caps, f"slice missing capability {expected}")

    def test_negative_existence_is_a_real_absence(self):
        # A named item that was never seeded must resolve to a deterministic ABSENCE,
        # never a false positive (the grounding guarantee for "Have I eaten X?").
        neg = next(s for s in SLICE_SPECS if s.id == "nutrition.existence_neg")
        user, anchors = self.built[neg.fixture]
        passed, _ = run_spec(user, neg, anchors)
        self.assertTrue(passed)


class CapabilityMatrixTests(TestCase):
    def test_matrix_marks_slice_capabilities_certified(self):
        m = capability_matrix()
        # weight (health) current/historical/timeline/comparison certified
        self.assertEqual(m["health"]["current_fact"], "certified")
        self.assertEqual(m["health"]["comparison"], "certified")
        # medicine list + existence + historical certified
        self.assertEqual(m["medicine"]["list"], "certified")
        self.assertEqual(m["medicine"]["existence"], "certified")
        self.assertEqual(m["medicine"]["historical"], "certified")
        # nutrition list + existence certified; date-scoped current is an honest GAP
        self.assertEqual(m["nutrition"]["list"], "certified")
        self.assertEqual(m["nutrition"]["existence"], "certified")
        self.assertEqual(m["nutrition"]["current_fact"], "gap")

    def test_matrix_covers_every_capability_for_every_domain(self):
        m = capability_matrix()
        for domain, row in m.items():
            self.assertEqual(set(row.keys()), set(CAPABILITIES),
                             f"{domain} missing capability columns")

    def test_matrix_summary_reports_counts(self):
        s = matrix_summary()
        self.assertGreaterEqual(s["certified"], 8)   # the slice certifies ≥ 8 cells
        self.assertIn("nutrition", s["slice_domains"])
