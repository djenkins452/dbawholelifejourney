# ==============================================================================
# File: apps/core/tests/test_truth_catalog.py
# Description: Platform capability — Truth Catalog (Capabilities). Enumerates the
#   answerable Layer 1 truth surface from registered Domain Truth Objects. No OpenAI.
# ==============================================================================
from django.test import SimpleTestCase

from apps.core.truth import catalog as CAT


class TruthCatalogTests(SimpleTestCase):
    def test_catalog_includes_registered_domains(self):
        cat = CAT.truth_catalog()
        self.assertIn("health", cat)
        self.assertIn("finance", cat)
        self.assertIn("current", cat["health"])
        self.assertIn("history", cat["health"])

    def test_can_answer_known_metrics(self):
        self.assertTrue(CAT.can_answer("health", "steps_today", "current"))
        self.assertTrue(CAT.can_answer("health", "steps", "history"))
        self.assertTrue(CAT.can_answer("finance", "net_worth", "current"))

    def test_cannot_answer_unknown(self):
        self.assertFalse(CAT.can_answer("health", "mood_today", "current"))
        self.assertFalse(CAT.can_answer("nope", "x", "current"))
        self.assertFalse(CAT.can_answer("finance", "net_worth", "history"))  # pending

    def test_summary_counts_the_surface(self):
        s = CAT.catalog_summary()
        self.assertGreaterEqual(s["domain_count"], 2)
        self.assertGreater(s["total_answerable"], 0)
        self.assertIn("health", s["domains"])
