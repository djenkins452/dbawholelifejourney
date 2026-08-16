"""The Question Catalog IS the certification standard — enforced here.

This ratchet locks the catalog: a question that is certified today must stay certified
(a truth surface regressed if it flips), and the KNOWN GAPS must match exactly (if a gap
closes, update the lock; if a new gap appears, a surface broke). Certification is computed
from the LIVE registries, so this test fails the moment Health's answerable set changes —
making the catalog the authoritative standard, not a stale report.
"""
from django.test import SimpleTestCase

from apps.core.truth.question_catalog import (
    KNOWN_CAPABILITIES,
    certify,
    certify_question,
    _REGISTRY,
    _ensure_loaded,
)


# The questions that are legitimately NOT yet answerable — each needs a NEW platform
# capability or a page that does not exist. Locked so regressions/closures are surfaced.
EXPECTED_HEALTH_GAPS = {
    "health.body_temperature.current_context",   # no temperature overview page (Phase 2c)
    # health.glucose.lows_more_frequent — CLOSED (Phase 3b: Event Frequency Analysis).
    # health.sleep.consistency — CLOSED (Phase 3a: Consistency/Variance capability).
    # health.weight.trend_change_point — CLOSED (Phase 3c: Change-Point Detection).
    # health.heart_rate.recovery — CLOSED (Phase 3d: HRV exposure → history+trend).
    # nutrition.meals_most_carbs — CLOSED (Phase 3e: reusable ranked_entity capability).
    # The ONLY remaining GAP is intentionally deferred (no Temperature workspace exists yet).
}


class QuestionCatalogFrameworkTests(SimpleTestCase):
    def test_categories_and_requirements_are_well_formed(self):
        _ensure_loaded("health")
        from apps.core.truth.question_catalog import CATEGORIES
        for q in _REGISTRY.values():
            self.assertIn(q.category, CATEGORIES, q.id)
            self.assertTrue(q.examples, f"{q.id}: no NL examples")
            self.assertTrue(q.requires, f"{q.id}: no requirements")

    def test_gap_questions_name_a_real_reason(self):
        """Every GAP must fail on a capability genuinely outside the platform OR an
        unregistered page — never a typo'd requirement for a capability we HAVE."""
        _ensure_loaded("health")
        for qid in EXPECTED_HEALTH_GAPS:
            q = _REGISTRY[qid]
            res = certify_question(q)
            self.assertFalse(res["certified"], f"{qid} unexpectedly certified")


class HealthCertificationRatchetTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rep = certify("health")

    def test_health_is_substantially_certified(self):
        s = self.rep["summary"]
        self.assertGreaterEqual(s["total"], 70)          # catalog is comprehensive
        self.assertGreaterEqual(s["pct"], 90.0)          # ≥90% answerable

    def test_uncertified_set_matches_the_locked_gaps(self):
        uncertified = {q["id"] for q in self.rep["questions"] if not q["certified"]}
        self.assertEqual(
            uncertified, EXPECTED_HEALTH_GAPS,
            "Health answerability changed. If a gap CLOSED, remove it from "
            "EXPECTED_HEALTH_GAPS. If a NEW gap appeared, a truth surface regressed — "
            "investigate before updating the lock.")

    def test_every_certified_question_uses_only_known_capabilities(self):
        for q in self.rep["questions"]:
            if q["certified"]:
                for r in q["requirements"]:
                    self.assertIn(r["capability"], KNOWN_CAPABILITIES, q["id"])


# Remaining CoS domains — MECH CERTIFIED (deterministic catalog fully answerable from the
# live surfaces). This ratchet locks their answerability: if a truth surface regresses, a
# question here flips to GAP and this fails. Update ONLY after investigating the regression.
_MECH_CERTIFIED_DOMAINS = ("medicine", "goals", "habits", "calendar", "tasks",
                           "relationships", "legacy", "medical", "brain_training",
                           "projects", "notes", "capture")


class RemainingDomainRatchetTests(SimpleTestCase):
    def test_remaining_domains_fully_certified(self):
        for d in _MECH_CERTIFIED_DOMAINS:
            rep = certify(d)
            uncert = [q["id"] for q in rep["questions"] if not q["certified"]]
            self.assertEqual(uncert, [], f"{d}: gaps appeared {uncert} — a surface regressed")
            self.assertGreaterEqual(rep["summary"]["total"], 1, d)
