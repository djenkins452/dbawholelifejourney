# ==============================================================================
# File: apps/core/truth/tests/test_retrieval_authority_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: PERMANENT platform contract — Retrieval Authority Metadata (F0)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-23
# ==============================================================================
"""
Retrieval Authority Metadata Contract — the enforceable platform gate.

    "A retrieval surface is not considered certified until every served value
     explicitly declares its authority and semantics."

This converts Retrieval Authority Certification from a documentation exercise into
a build gate. It fails automatically when:
  * a served key omits authority/semantics metadata (architecturally anonymous),
  * a declaration uses a vocabulary term outside the contract,
  * a key claims to be a projection without naming the canonical authority it defers to,
  * a NEW shadow / missing-projection is introduced (the ratchet).

Closing a known defect is a DELIBERATE edit to `KNOWN_DEFECTS` below — which is the
point: the remaining residuals are now countable, and progress is visible in a diff.
"""
from django.test import SimpleTestCase

from apps.core.truth import authority as A


class AuthorityVocabularyTests(SimpleTestCase):
    """The vocabulary is deliberately small; validation is strict."""

    def _decl(self, **kw):
        base = dict(authority="X", semantics=A.EXACT_DATE,
                    truth_category=A.CATEGORY_METRIC,
                    classification=A.CANONICAL_AUTHORITY)
        base.update(kw)
        return A.AuthorityDeclaration(**base)

    def test_valid_declaration_passes(self):
        self.assertEqual(A.validate("k", self._decl()), [])

    def test_anonymous_authority_is_rejected(self):
        errs = A.validate("k", self._decl(authority=""))
        self.assertTrue(any("anonymous" in e for e in errs), errs)

    def test_unknown_semantics_rejected(self):
        errs = A.validate("k", self._decl(semantics="vibes"))
        self.assertTrue(any("unknown semantics" in e for e in errs), errs)

    def test_projection_must_name_its_canonical_authority(self):
        errs = A.validate("k", self._decl(classification=A.PROJECTION_OF))
        self.assertTrue(any("delegates_to" in e for e in errs), errs)
        # ...and passes once it does.
        self.assertEqual(
            A.validate("k", self._decl(classification=A.PROJECTION_OF,
                                       delegates_to="get_domain_history:health.weight")),
            [])

    def test_canonical_authority_may_not_also_delegate(self):
        errs = A.validate("k", self._decl(delegates_to="something"))
        self.assertTrue(any("cannot both own and defer" in e for e in errs), errs)

    def test_undeclared_served_key_is_a_violation(self):
        errs = A.validate_surface({"a": self._decl()}, served_keys={"a", "b"})
        self.assertTrue(any(e.startswith("b:") and "UNDECLARED" in e for e in errs), errs)

    def test_duplicate_answer_pairs_detected(self):
        d = self._decl()
        dupes = A.duplicate_answers({"k1": d, "k2": d})
        self.assertIn((d.authority, d.semantics), dupes)


class FoundationalHealthFactsContractTests(SimpleTestCase):
    """The first surface bound to the contract. Every served key must be declared."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apps.ai.cos_services import health_facts as hf
        cls.hf = hf
        cls.declarations = hf.authority_declarations()
        cls.served = hf.served_keys()

    def test_every_served_key_declares_authority_and_semantics(self):
        errs = A.validate_surface(self.declarations, served_keys=self.served)
        self.assertEqual(errs, [], "Retrieval Authority Metadata Contract violations:\n"
                                   + "\n".join(errs))

    def test_no_key_is_architecturally_anonymous(self):
        for key, decl in self.declarations.items():
            self.assertTrue(decl.authority, f"{key} declares no authority")
            self.assertIn(decl.semantics, A.SEMANTICS, f"{key} semantics")
            self.assertIn(decl.classification, A.CLASSIFICATIONS, f"{key} classification")

    def test_every_projection_references_a_canonical_authority(self):
        for key, decl in self.declarations.items():
            if decl.classification == A.PROJECTION_OF:
                self.assertTrue(
                    decl.delegates_to,
                    f"{key} is a projection but names no canonical authority")

    def test_derived_day_keys_all_delegate(self):
        """The ~100 derived <metric>_today/_yesterday keys must every one be a
        projection of the systematic history authority — never their own producer.

        Selected by DECLARED authority, never by name suffix: `_today` is not a
        reliable classifier (`medication_execution_today` / `supplement_execution_today`
        are Medicine inventory keys, not date-scoped metrics). That naming ambiguity is
        the exact condition this contract exists to remove — so the test reads the
        declaration, not the key name.
        """
        day_keys = [k for k, d in self.declarations.items()
                    if d.authority.startswith("metric_date.metric_on_date:")]
        self.assertGreater(len(day_keys), 50, "derived day-key set collapsed")
        for key in day_keys:
            decl = self.declarations[key]
            self.assertEqual(decl.classification, A.PROJECTION_OF, key)
            self.assertEqual(decl.semantics, A.EXACT_DATE, key)
            self.assertTrue(decl.delegates_to.startswith("get_domain_history:"), key)

    # ---- THE RATCHET -----------------------------------------------------
    # The known architectural defects, pinned. A NEW shadow/missing-projection fails
    # the build. Closing one is a deliberate deletion from this set.
    # Tracked in docs/WLJ_RETRIEVAL_PLATFORM_CERTIFICATION.md (F1-F6).
    KNOWN_DEFECTS = {
        "average_glucose_yesterday": A.SHADOW_AUTHORITY,   # F1 rename
        "last_glucose_reading": A.SHADOW_AUTHORITY,        # F2 delegate
        "steps_recent": A.SHADOW_AUTHORITY,                # F3 rename
        "latest_meal_logged": A.SHADOW_AUTHORITY,          # F4 delegate
        "average_sleep_7d": A.SHADOW_AUTHORITY,            # F5
        "sleep_trend": A.SHADOW_AUTHORITY,                 # F5
        "weight_30_day_change": A.SHADOW_AUTHORITY,        # F5
        "last_blood_pressure_reading": A.MISSING_PROJECTION,  # F6 composite projection
    }

    def test_no_new_shadow_or_missing_authority_is_introduced(self):
        found = A.defects(self.declarations)
        new = {k: v for k, v in found.items() if k not in self.KNOWN_DEFECTS}
        self.assertEqual(
            new, {},
            "NEW retrieval authority defect(s) introduced. Either delegate to the "
            "canonical authority, or (if deliberate) add to KNOWN_DEFECTS with a "
            "certification finding id:\n" + repr(new))

    def test_closed_defects_are_removed_from_the_ratchet(self):
        """When a defect is fixed, its pin must be deleted — otherwise the ratchet
        silently stops protecting that key."""
        found = A.defects(self.declarations)
        stale = {k for k in self.KNOWN_DEFECTS if k not in found}
        self.assertEqual(
            stale, set(),
            f"These keys are no longer defects — remove them from KNOWN_DEFECTS: {stale}")
