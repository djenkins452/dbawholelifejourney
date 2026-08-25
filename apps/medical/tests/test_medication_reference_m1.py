# ==============================================================================
# File: apps/medical/tests/test_medication_reference_m1.py
# Description: Contract — MEDICATION REFERENCE TRUTH (M1). Authoritative, impersonal
#   product labelling is a SEPARATE truth domain from the person's own regimen; its
#   identity chain is the safety gate and it FAILS CLOSED. Deterministic only: every
#   outbound call is mocked, and one test proves the truth surface makes none at all.
#   Design of record: docs/WLJ_MEDICATION_INSTRUCTION_TRUTH_INVESTIGATION.md Part B.
# ==============================================================================
import json
from datetime import date, time
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.health.models import Intake, IntakeSchedule
from apps.medical.models import MedicationProductLabel
from apps.medical.services import medication_reference as ref
from apps.users.models import TermsAcceptance

# Verbatim-shaped fixture text. The point of the verbatim tests is that whatever
# arrives is what is stored and exposed — never a WLJ-authored condensation.
LABEL_TEXT = ("2 DOSAGE AND ADMINISTRATION • Administer once weekly, any time of day, "
              "with or without meals. • If a dose is missed, administer as soon as "
              "possible within 4 days (96 hours) after the missed dose.")


def _fake_api(name_rxcui=None, tty="BN", spls=None, label=None):
    """Route mocked JSON by URL so each gate can be driven independently."""
    def _get(url):
        if "rxcui.json?name=" in url:
            return {"idGroup": {"rxnormId": name_rxcui}} if name_rxcui else {"idGroup": {}}
        if "property.json?propName=TTY" in url:
            return {"propConceptGroup": {"propConcept": [{"propValue": tty}]}}
        if "/spls.json?rxcui=" in url:
            return {"data": spls if spls is not None else []}
        if "api.fda.gov" in url:
            return {"results": [label]} if label else {}
        return None
    return _get


SPL_MANUFACTURER = {"setid": "aaaa-1111", "spl_version": 20,
                    "published_date": "Jun 10, 2026",
                    "title": "BRANDX (MOLECULE) INJECTION, SOLUTION [REAL MAKER INC]"}
SPL_REPACKAGER = {"setid": "bbbb-2222", "spl_version": 3,
                  "published_date": "Nov 22, 2023",
                  "title": "BRANDX (MOLECULE) INJECTION, SOLUTION [A-S REPACKAGER]"}
OPENFDA_LABEL = {"set_id": "aaaa-1111", "version": "20", "effective_time": "20260601",
                 "dosage_and_administration": [LABEL_TEXT],
                 "openfda": {"brand_name": ["BrandX"], "generic_name": ["MOLECULE"]}}


class IdentityChainContractTests(SimpleTestCase):
    """Identity correctness is the primary safety gate. Every gate must pass."""

    def test_brand_name_resolves(self):
        with mock.patch.object(ref, "_get_json", _fake_api(["111"], "BN")):
            out = ref.resolve_identity("BrandX")
        self.assertEqual(out.state, "resolved")
        self.assertEqual(out.payload["rxcui"], "111")

    def test_multi_source_generic_is_unsupported_not_guessed(self):
        """M1 scope boundary: an ingredient concept is a multi-source generic."""
        for tty in ("IN", "PIN", "SCD"):
            with mock.patch.object(ref, "_get_json", _fake_api(["222"], tty)):
                out = ref.resolve_identity("metformin")
            self.assertEqual(out.state, "unsupported", f"TTY {tty} must be unsupported")
            self.assertIn("generic", out.note.lower())

    def test_multiple_concepts_for_one_name_fail_closed(self):
        with mock.patch.object(ref, "_get_json", _fake_api(["1", "2"], "BN")):
            out = ref.resolve_identity("Ambiguous Thing")
        self.assertEqual(out.state, "ambiguous")

    def test_unknown_name_is_unsupported(self):
        with mock.patch.object(ref, "_get_json", _fake_api(None)):
            self.assertEqual(ref.resolve_identity("zzz").state, "unsupported")

    def test_identity_success_does_not_imply_a_label_exists(self):
        """Proven live: 'fish oil' resolves to an RXCUI and has no drug label. The two
        are separate gates, so a resolved identity must never imply label truth."""
        with mock.patch.object(ref, "_get_json", _fake_api(["4419"], "BN", spls=[])):
            out = ref.resolve_medication_label("Fish Oil")
        self.assertEqual(out.state, "no_label")


class LabelSelectionContractTests(SimpleTestCase):
    """Never 'first search result'; never a title match; ties fail closed."""

    def test_highest_version_labeler_of_record_wins(self):
        with mock.patch.object(ref, "_get_json", _fake_api(
                ["111"], "BN", spls=[SPL_REPACKAGER, SPL_MANUFACTURER])):
            out = ref.select_label_document("111")
        self.assertEqual(out.state, "resolved")
        self.assertEqual(out.payload["spl"]["setid"], "aaaa-1111",
                         "must select the actively-revised label, not the first row")

    def test_two_labelers_tied_at_top_version_fail_closed(self):
        tie = dict(SPL_REPACKAGER, spl_version=20, setid="cccc-3333")
        with mock.patch.object(ref, "_get_json", _fake_api(
                ["111"], "BN", spls=[SPL_MANUFACTURER, tie])):
            out = ref.select_label_document("111")
        self.assertEqual(out.state, "ambiguous")
        self.assertIn("labeler", out.note)

    def test_selection_is_keyed_on_rxcui_never_on_a_name(self):
        """The proven wrong-product vector: DailyMed's top NAME match for 'Ozempic' is
        an ORAL TABLET (Rybelsus) SPL. Resolution must never issue a name query."""
        seen = []

        def _spy(url):
            seen.append(url)
            return _fake_api(["111"], "BN", spls=[SPL_MANUFACTURER],
                             label=OPENFDA_LABEL)(url)

        with mock.patch.object(ref, "_get_json", _spy):
            ref.resolve_medication_label("BrandX")
        spl_calls = [u for u in seen if "/spls.json" in u]
        self.assertTrue(spl_calls)
        for u in spl_calls:
            self.assertIn("rxcui=", u)
            self.assertNotIn("drug_name=", u)


class VerbatimAndProvenanceContractTests(TestCase):
    """WLJ stores and exposes the label's own words, with provenance — and never
    authors clinical content of its own (Constitution I.4)."""

    def _resolve(self):
        with mock.patch.object(ref, "_get_json", _fake_api(
                ["111"], "BN", spls=[SPL_MANUFACTURER, SPL_REPACKAGER],
                label=OPENFDA_LABEL)):
            out = ref.resolve_medication_label("BrandX")
        return ref.persist(out, "BrandX")

    def test_stored_text_is_byte_identical_to_the_source(self):
        row = self._resolve()
        self.assertEqual(row.dosage_and_administration, LABEL_TEXT,
                         "WLJ must never paraphrase, summarize or condense a label")

    def test_provenance_identifies_exactly_which_label_this_is(self):
        row = self._resolve()
        self.assertEqual(row.spl_setid, "aaaa-1111")
        self.assertEqual(row.spl_version, "20")
        self.assertEqual(row.source, "dailymed")
        self.assertEqual(row.effective_time, "20260601")
        self.assertIn("aaaa-1111", row.source_url)
        self.assertTrue(row.retrieved_at)
        self.assertTrue(row.content_hash)
        # identity authority and text retrieval are recorded separately, never conflated
        self.assertNotEqual(row.source, row.content_source)

    def test_a_refusal_persists_no_label(self):
        with mock.patch.object(ref, "_get_json", _fake_api(["222"], "IN")):
            out = ref.resolve_medication_label("metformin")
        self.assertIsNone(ref.persist(out, "metformin"))
        self.assertEqual(MedicationProductLabel.objects.count(), 0)

    def test_the_record_is_impersonal(self):
        """No user FK, by design — this is a fact about a product, not a person."""
        fields = {f.name for f in MedicationProductLabel._meta.get_fields()}
        for personal in ("user", "owner", "intake", "patient"):
            self.assertNotIn(personal, fields)


class _DomainCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="medref@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.brand = Intake.objects.create(
            user=self.user, name="BrandX", dose="10mg", frequency="weekly",
            start_date=date(2026, 1, 1), intake_status="active",
            intake_type="medication", category="prescription")
        IntakeSchedule.objects.create(intake=self.brand, scheduled_time=time(7, 0),
                                      days_of_week="0", is_active=True)
        self.generic = Intake.objects.create(
            user=self.user, name="Metformin HCL ER", dose="500mg", frequency="daily",
            start_date=date(2026, 1, 1), intake_status="active",
            intake_type="medication", category="prescription")

    def _link_brand(self):
        with mock.patch.object(ref, "_get_json", _fake_api(
                ["111"], "BN", spls=[SPL_MANUFACTURER], label=OPENFDA_LABEL)):
            ref.resolve_and_link_intake(self.brand)

    def _link_generic(self):
        with mock.patch.object(ref, "_get_json", _fake_api(["222"], "PIN")):
            ref.resolve_and_link_intake(self.generic)


class AcceptanceContractTests(_DomainCase):
    """The two acceptance cases: a resolvable brand, and a generic that must refuse."""

    def test_brand_product_yields_authoritative_truth(self):
        self._link_brand()
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "medication_reference", name="BrandX")
        self.assertEqual(env.get("status"), "ready", env)
        ent = env["entity"]
        # assert on STRUCTURE, not a serialized blob: the verbatim text must arrive
        # as the label's own words, unaltered.
        self.assertEqual(ent["plan"]["dosage_and_administration"], LABEL_TEXT,
                         "the verbatim label must reach the model unedited")
        self.assertIs(ent["plan"]["verbatim"], True)
        prov = ent["standing"]["provenance"]
        self.assertEqual(prov["spl_setid"], "aaaa-1111")
        self.assertEqual(prov["source"], "dailymed")
        self.assertEqual(prov["spl_version"], "20")

    def test_unresolved_generic_never_receives_a_guessed_label(self):
        """Expected behaviour for M1, not a defect: refusing beats attaching the
        wrong manufacturer's label."""
        self._link_generic()
        self.generic.refresh_from_db()
        self.assertEqual(self.generic.reference_identity_confidence, "unsupported")
        self.assertEqual(self.generic.reference_spl_setid, "")

        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "medication_reference",
                                name="Metformin HCL ER")
        blob = json.dumps(env)
        self.assertNotIn(LABEL_TEXT, blob,
                         "another product's label leaked onto an unresolved generic")
        self.assertIn("unavailable", blob.lower())
        # and it says so honestly rather than returning nothing
        self.assertIn("do NOT supply the product's instructions", blob)

    def test_identity_link_is_recorded_for_audit(self):
        self._link_brand()
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.reference_identity_confidence, "exact")
        self.assertEqual(self.brand.reference_spl_setid, "aaaa-1111")
        self.assertEqual(self.brand.reference_rxcui, "111")
        self.assertIsNotNone(self.brand.reference_resolved_at)


class OwnershipBoundaryContractTests(_DomainCase):
    """No parallel authority, in EITHER direction."""

    def test_medicine_never_serves_product_label_facts(self):
        self._link_brand()
        from apps.health.services.medicine_queries import MedicineQueries
        blob = json.dumps([e.to_dict() for e in MedicineQueries.describe(self.user)],
                          default=str)
        self.assertNotIn(LABEL_TEXT, blob,
                         "product labelling leaked into the personal medicine domain")
        for leaked in ("spl_setid", "dosage_and_administration", "dailymed"):
            self.assertNotIn(leaked, blob)

    def test_medication_reference_never_serves_personal_regimen_facts(self):
        self._link_brand()
        from apps.ai.cos_services.domain_entity import get_domain_entity
        ent = get_domain_entity(
            self.user, "medication_reference", name="BrandX")["entity"]

        # Prose that POINTS AT the other domain is the boundary being advertised, not
        # a leak — so strip the explanatory keys and inspect the actual FACTS.
        def _facts(block):
            return {k: v for k, v in (ent.get(block) or {}).items()
                    if k not in ("scope", "means", "verbatim")}

        for block in ("definition", "plan", "performance"):
            keys = " ".join(_facts(block)).lower()
            for personal in ("adherence", "last_taken", "schedule",
                             "recorded_instructions", "marked_late_after_minutes",
                             "dose_today", "taken"):
                self.assertNotIn(personal, keys,
                                 f"personal regimen fact {personal!r} leaked into "
                                 f"impersonal reference truth (`{block}`)")
        # `standing` carries only provenance + identity resolution — nothing personal
        self.assertEqual(set(ent["standing"]), {"provenance", "identity_resolution"})
        self.assertEqual(_facts("performance"), {})

    def test_exactly_one_producer_for_the_domain(self):
        from apps.core.truth.domain import get_domain_truth
        from apps.medical.services.medication_reference_domain_truth import (
            MedicationReferenceDomainTruth,
        )
        self.assertIsInstance(get_domain_truth(self.user, "medication_reference"),
                              MedicationReferenceDomainTruth)


class RequestPathSafetyContractTests(_DomainCase):
    def test_the_truth_surface_makes_no_outbound_call(self):
        """A cache miss must return an honest unavailable state — never a live fetch."""
        from apps.ai.cos_services.domain_entity import get_domain_entity

        def _explode(*a, **k):
            raise AssertionError("outbound HTTP on the CoS request path")

        with mock.patch("urllib.request.urlopen", _explode), \
             mock.patch.object(ref, "_get_json", _explode):
            env = get_domain_entity(self.user, "medication_reference", name="BrandX")
        self.assertIn("unavailable", json.dumps(env).lower())

    def test_refresh_is_scheduled_as_crontab_not_an_interval(self):
        """Railway's ephemeral filesystem resets PersistentScheduler, starving
        long-interval tasks — the beat-durability contract requires crontab."""
        from celery.schedules import crontab
        entries = [e for e in settings.CELERY_BEAT_SCHEDULE.values()
                   if e.get("task") == "medical.refresh_medication_reference_labels"]
        self.assertEqual(len(entries), 1)
        self.assertIsInstance(entries[0]["schedule"], crontab)


class DiscoveryAndToolSurfaceContractTests(SimpleTestCase):
    def test_capability_index_advertises_the_domain(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("product_label",
                      caps["truth_entities"].get("medication_reference", []))
        sem = caps["domain_semantics"].get("medication_reference") or {}
        text = json.dumps(sem).lower()
        self.assertIn("impersonal", text)
        self.assertIn("verbatim", text)
        # the boundary to personal truth is advertised, so both get retrieved
        self.assertIn("'medicine' domain", json.dumps(sem))
        # and the honest-refusal contract is advertised
        self.assertIn("refuses", text)

    def test_medicine_points_at_the_reference_domain(self):
        from apps.core.truth.semantics import domain_semantics
        med = domain_semantics("medicine")["entities"]["medication"]
        self.assertIn("medication_reference", med)
        self.assertIn("retrieve BOTH", med)

    def test_no_new_retrieval_tool_was_added(self):
        """M1 must reach the model through the EXISTING get_entity surface."""
        from apps.ai.model_interface.constitution import all_tools
        names = {t["function"]["name"] for t in all_tools(writes_enabled=True)}
        for invented in ("get_medication_reference", "get_product_label",
                         "get_label", "get_drug_label", "lookup_medication"):
            self.assertNotIn(invented, names)
        ge = [t for t in all_tools(writes_enabled=False)
              if t["function"]["name"] == "get_entity"][0]
        enum = ge["function"]["parameters"]["properties"]["domain"].get("enum") or []
        self.assertIn("medication_reference", enum,
                      "the domain must be reachable through the existing tool")

    def test_wlj_authors_no_clinical_interpretation(self):
        """Nothing in the producer may generate clinical prose — WLJ carries the
        label's words and its own non-clinical provenance labels only."""
        import inspect

        from apps.medical.services import medication_reference_domain_truth as dt
        src = inspect.getsource(dt).lower()
        for authored in ("you can take", "it is safe", "should take", "mg ",
                         "within 4 days", "96 hours", "mounjaro", "tirzepatide"):
            self.assertNotIn(authored, src,
                             f"WLJ appears to author clinical content: {authored!r}")
