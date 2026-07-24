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
from django.test import SimpleTestCase, TestCase

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


# ---------------------------------------------------------------------------
# ADOPTED SURFACE REGISTRY (platform adoption, Phase 1).
# Every keyed retrieval surface that has adopted the metadata contract lists itself
# here by (label, module). A surface adopts by exposing `authority_declarations()`
# and `served_keys()`. Adding a surface here binds it to the SAME mechanical gate —
# no per-surface test authoring. Composed-envelope surfaces (get_domain_state,
# standing_context, executive briefings, decision authority) carry provenance at the
# ENVELOPE level and are verified separately (see WLJ_PLATFORM_ADOPTION_ROLLOUT.md).
_ADOPTED_SURFACES = [
    ("get_foundational_health_facts", "apps.ai.cos_services.health_facts"),
    ("get_foundational_execution_facts", "apps.ai.cos_services.execution_facts"),
]


def _load_surface(module_path):
    import importlib
    mod = importlib.import_module(module_path)
    return mod.authority_declarations(), mod.served_keys()


class AdoptedSurfacesContractTests(SimpleTestCase):
    """Every ADOPTED keyed surface passes the contract mechanically — no surface may
    serve an anonymous value, and every projection names its canonical authority."""

    def test_every_adopted_surface_is_fully_declared(self):
        for label, module_path in _ADOPTED_SURFACES:
            with self.subTest(surface=label):
                declarations, served = _load_surface(module_path)
                errs = A.validate_surface(declarations, served_keys=served)
                self.assertEqual(errs, [], f"{label} contract violations:\n"
                                           + "\n".join(errs))

    def test_every_adopted_projection_names_its_authority(self):
        for label, module_path in _ADOPTED_SURFACES:
            declarations, _ = _load_surface(module_path)
            for key, decl in declarations.items():
                if decl.classification == A.PROJECTION_OF:
                    self.assertTrue(decl.delegates_to,
                                    f"{label}:{key} projection names no authority")


class ComposedSurfaceContractTests(TestCase):
    """Composed-envelope surfaces serve ONE composed object per call, so they declare
    `authority` + `semantics` at the envelope ROOT (not per-scalar). This verifies the
    Wave-2 adoptions carry both fields with a contract-valid semantics value."""

    def _user(self):
        from django.conf import settings
        from django.contrib.auth import get_user_model
        from apps.users.models import TermsAcceptance
        U = get_user_model()
        u = U.objects.create_user(email="composed@example.com", password="x")
        TermsAcceptance.objects.create(
            user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        u.preferences.has_completed_onboarding = True
        u.preferences.save()
        return u

    def _assert_declared(self, envelope, label):
        self.assertIsInstance(envelope, dict, label)
        self.assertTrue(envelope.get("authority"), f"{label}: no authority at root")
        self.assertIn(envelope.get("semantics"), A.SEMANTICS,
                      f"{label}: semantics {envelope.get('semantics')!r} not in vocabulary")

    def test_domain_state_declares_at_root(self):
        from apps.ai.cos_services.domain_state import get_domain_state
        self._assert_declared(get_domain_state(self._user(), "health"), "domain_state")

    def test_decision_authority_declares_at_root(self):
        from apps.core.execution.decision_authority import current_action, execution_facts
        u = self._user()
        self._assert_declared(current_action(u), "decision_authority.current_action")
        self._assert_declared(execution_facts(u), "execution_state")

    def test_executive_briefing_declares_at_root(self):
        from apps.core.truth.briefing import build_executive_briefing
        self._assert_declared(build_executive_briefing(self._user()).to_dict(),
                              "executive_briefing")

    def test_standing_context_declares_at_root(self):
        # No warm cache in test → the pending shell, which is also declared.
        from apps.ai.cos_services.standing_context import get_standing_context
        self._assert_declared(get_standing_context(self._user()), "standing_context")

    def test_page_summary_declares_via_choke_point(self):
        # Every page summary is stamped at the ONE resolution choke point. Register a
        # throwaway provider and resolve it through the real path.
        from apps.core import current_context as cc
        cc.register_page_summary("_cert_probe")(
            lambda user, params: {"title": "T", "content": "C"})
        try:
            summ = cc._resolve_page_summary(self._user(), "summary:_cert_probe")
        finally:
            cc._PAGE_SUMMARY_PROVIDERS.pop("_cert_probe", None)
        self._assert_declared(summ, "page_summary")
        self.assertEqual(summ["semantics"], "projection")


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
        # Wave 3: the three rolling averages now DELEGATE to get_history (compliant
        # projections); average_glucose_yesterday/steps_recent RENAMED to honest 7d
        # names. weight_30_day_change and sleep_trend remain — reclassified
        # MISSING_PROJECTION: get_history exposes series average/total but not a
        # change/trend scalar, so the canonical projection is genuinely absent (not a
        # duplicate authority). Closing them = teach get_history to own change/trend.
        "sleep_trend": A.MISSING_PROJECTION,
        "weight_30_day_change": A.MISSING_PROJECTION,
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
