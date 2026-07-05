"""GEDCOM: structured genealogy stays structured — never flattened into stories."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.legacy.services import gedcom_parser
from apps.legacy.services.import_engine import create_batch, import_chunks, review_queues

User = get_user_model()

SAMPLE = """0 HEAD
1 SOUR TestApp
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME Marvin /Jenkins/
1 SEX M
1 BIRT
2 DATE 3 MAR 1945
2 PLAC Knoxville, Tennessee
1 DEAT
2 DATE 12 DEC 2010
2 PLAC Maryville, Tennessee
0 @I2@ INDI
1 NAME Betty /Jenkins/
1 SEX F
1 BIRT
2 DATE 1948
0 @I3@ INDI
1 NAME Danny /Jenkins/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 MARR
2 DATE 1970
2 PLAC Knoxville, Tennessee
0 TRLR
"""


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class GedcomParserTests(TestCase):
    def test_detection(self):
        self.assertTrue(gedcom_parser.looks_like_gedcom(SAMPLE))
        self.assertFalse(gedcom_parser.looks_like_gedcom(
            "My dad took me fishing at the lake and we talked for hours."))

    def test_parses_people_and_families(self):
        chunks = gedcom_parser.parse_gedcom(SAMPLE)
        people = [c for c in chunks if c["kind"] == "gedcom_person"]
        fams = [c for c in chunks if c["kind"] == "gedcom_family"]
        self.assertEqual(len(people), 3)
        self.assertEqual(len(fams), 1)
        marvin = next(c for c in people if c["title"] == "Marvin Jenkins")
        self.assertIn("Born 3 MAR 1945 in Knoxville, Tennessee", marvin["body"])
        self.assertIn("Died 12 DEC 2010 in Maryville, Tennessee", marvin["body"])
        fam = fams[0]
        self.assertEqual(fam["title"], "Marvin Jenkins & Betty Jenkins")
        self.assertIn("Married 1970 in Knoxville, Tennessee", fam["body"])
        self.assertIn("Children: Danny Jenkins", fam["body"])

    def test_malformed_gedcom_does_not_raise(self):
        self.assertEqual(gedcom_parser.parse_gedcom("garbage\nnot gedcom\n"), [])

    def test_narrative_note_split_into_discovery_unit(self):
        ged = (
            "0 HEAD\n0 @I1@ INDI\n1 NAME Marvin /Jenkins/\n1 SEX M\n1 BIRT\n2 DATE 1945\n"
            "1 NOTE Marvin loved to fish. Every summer he would take the whole\n"
            "2 CONT family to the lake before dawn and we spent the entire day out\n"
            "2 CONT on the water telling stories and laughing together.\n0 TRLR\n")
        chunks = gedcom_parser.parse_gedcom(ged)
        notes = [c for c in chunks if not c.get("kind")]
        people = [c for c in chunks if c.get("kind") == "gedcom_person"]
        self.assertEqual(len(notes), 1)                    # note became its own unit
        self.assertIn("Note about Marvin Jenkins", notes[0]["title"])
        self.assertIn("loved to fish", notes[0]["body"])
        self.assertNotIn("loved to fish", people[0]["body"])   # split OUT of the structured record

    def test_short_note_stays_with_record(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME Bo /Kin/\n1 NOTE Nickname was Bo.\n0 TRLR\n")
        chunks = gedcom_parser.parse_gedcom(ged)
        self.assertTrue(all(c.get("kind") == "gedcom_person" for c in chunks))
        self.assertIn("Nickname was Bo.", chunks[0]["body"])


class GedcomImportTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def _boom(self, units):
        raise AssertionError("AI classifier must not run for structured GEDCOM")

    def test_autodetect_even_when_type_is_wrong(self):
        # User picked "plain_text" but uploaded a GEDCOM — Legacy recognizes it.
        batch = create_batch(self.user, "Family tree", "plain_text", SAMPLE,
                             classifier=self._boom)
        self.assertEqual(batch.source_type, "gedcom")
        kinds = set(batch.chunks.values_list("chunk_kind", flat=True))
        self.assertEqual(kinds, {"gedcom_person", "gedcom_family"})
        self.assertFalse(batch.chunks.filter(chunk_kind="story").exists())

    def test_genealogy_never_becomes_stories(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=self._boom)
        mems = import_chunks(batch, run_discovery=False)   # bulk import
        self.assertEqual(mems, [])                          # nothing narrative → no stories
        self.assertEqual(batch.chunks.filter(status="imported").count(), 0)

    def test_review_queues_include_genealogy(self):
        batch = create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=self._boom)
        queues = {q["kind"]: q for q in review_queues(batch)}
        self.assertIn("gedcom_person", queues)
        self.assertIn("gedcom_family", queues)
        self.assertEqual(queues["gedcom_person"]["count"], 3)
        self.assertFalse(queues["gedcom_person"]["is_narrative"])

    def test_only_notes_go_through_classifier(self):
        ged = (
            "0 HEAD\n0 @I1@ INDI\n1 NAME Marvin /Jenkins/\n1 BIRT\n2 DATE 1945\n"
            "1 NOTE Marvin loved to fish and would take the whole family to the lake "
            "every single summer before dawn, and we spent the entire day out on the "
            "water telling stories and laughing together until the sun went down.\n0 TRLR\n")
        calls = {"n": 0}

        def classifier(units):
            calls["n"] += 1
            return {u["index"]: ("story", "high") for u in units}

        batch = create_batch(self.user, "Tree", "gedcom", ged, classifier=classifier)
        self.assertEqual(calls["n"], 1)   # classifier ran ONCE, for the note only
        kinds = set(batch.chunks.values_list("chunk_kind", flat=True))
        self.assertIn("gedcom_person", kinds)   # structured, bypassed the classifier
        self.assertIn("story", kinds)           # the note, classified


# A record loaded with facts Legacy has no canonical home for — the whole point
# of the preservation guarantee. Occupation, religion, baptism, burial, residence,
# immigration, military, a source citation, and a custom (_XXXX) tag.
RICH = """0 HEAD
0 @I1@ INDI
1 NAME Marvin /Jenkins/
1 SEX M
1 BIRT
2 DATE 3 MAR 1945
1 OCCU Railroad conductor
1 RELI Baptist
1 BAPM
2 DATE 1 JUN 1945
2 PLAC First Baptist, Knoxville
1 RESI
2 PLAC Maryville, Tennessee
1 IMMI
2 DATE 1948
1 BURI
2 PLAC Grandview Cemetery
1 _MILT US Army, WWII
1 SOUR State of Tennessee birth index
0 TRLR
"""


class GedcomPreservationTests(TestCase):
    """Nothing in a source is silently discarded — every fact is preserved and
    the completeness report explains what has no canonical home yet."""

    def test_every_fact_is_preserved(self):
        chunks = gedcom_parser.parse_gedcom(RICH)
        person = next(c for c in chunks if c["kind"] == "gedcom_person")
        tags = {f["tag"] for f in person["data"]["facts"]}
        # Facts Legacy can't store yet are STILL kept on the chunk — not dropped.
        for tag in ("OCCU", "RELI", "BAPM", "RESI", "IMMI", "BURI", "_MILT", "SOUR"):
            self.assertIn(tag, tags)
        occu = next(f for f in person["data"]["facts"] if f["tag"] == "OCCU")
        self.assertEqual(occu["value"], "Railroad conductor")
        bapm = next(f for f in person["data"]["facts"] if f["tag"] == "BAPM")
        self.assertEqual(bapm["place"], "First Baptist, Knoxville")

    def test_coverage_classifies_supported_needs_and_unknown(self):
        chunks = gedcom_parser.parse_gedcom(RICH)
        report = gedcom_parser.analyze_coverage(chunks)
        supported = {r["concept"] for r in report["supported"]}
        self.assertIn("People", supported)
        self.assertIn("Births", supported)
        # needs_support is grouped by CONCEPT (conceptual, not structural):
        # Occupation→Career, Religion/Baptism→Faith Journey, Burial→Life Events, …
        needs = {r["concept"] for r in report["needs_support"]}
        for concept in ("Career", "Faith Journey", "Places", "Immigration",
                        "Life Events", "Sources & Citations"):
            self.assertIn(concept, needs)
        # The granular fact-types are preserved as labels under each concept.
        faith = next(r for r in report["needs_support"] if r["concept"] == "Faith Journey")
        self.assertIn("Baptism", faith["labels"])
        self.assertIn("Religion", faith["labels"])
        # A custom tag Legacy doesn't recognize is preserved and surfaced, not lost.
        self.assertIn("_MILT", {r["tag"] for r in report["unknown"]})

    def test_nothing_is_discarded_total(self):
        chunks = gedcom_parser.parse_gedcom(RICH)
        report = gedcom_parser.analyze_coverage(chunks)
        # preserved_total must account for the person + every fact captured.
        person = next(c for c in chunks if c["kind"] == "gedcom_person")
        self.assertEqual(report["preserved_total"],
                         len(person["data"]["facts"]) + 1)

    def test_create_batch_stores_coverage_report(self):
        u = _make_user("preserve@example.com")
        batch = create_batch(u, "Tree", "gedcom", RICH,
                             classifier=lambda units: {})
        self.assertIn("needs_support", batch.coverage)
        needs = {r["concept"] for r in batch.coverage["needs_support"]}
        self.assertIn("Career", needs)


# A father (M), a mother (F), their child; the father also married a second woman
# (a step-mother by marriage); and an adopted child in a separate family.
TYPED = """0 HEAD
0 @I1@ INDI
1 NAME Marvin /Jenkins/
1 SEX M
0 @I2@ INDI
1 NAME Barbara /Dorff/
1 SEX F
0 @I3@ INDI
1 NAME Danny /Jenkins/
1 SEX M
1 BIRT
2 DATE 1971
0 @I4@ INDI
1 NAME Gloria /Katzell/
1 SEX F
0 @I5@ INDI
1 NAME Adam /Poe/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I4@
1 CHIL @I5@
2 _FREL Adopted
2 _MREL Adopted
1 MARR
2 DATE 1980
0 TRLR
"""


class ImporterTypesRelationshipsTests(TestCase):
    """The importer produces the most accurate canonical type from the evidence the
    GEDCOM already carries — SEX, marriage, pedigree — never a generic 'Parent'."""

    def _commit(self, email, ged=TYPED):
        from apps.legacy.services.import_engine import commit_genealogy
        u = _make_user(email)
        batch = create_batch(u, "Tree", "gedcom", ged, classifier=lambda units: {})
        commit_genealogy(batch)
        return u

    def _rel(self, u, frm, to):
        from apps.legacy.models import Person, Relationship
        a = Person.objects.get(user=u, display_name=frm)
        b = Person.objects.get(user=u, display_name=to)
        r = Relationship.objects.filter(user=u, from_person=a, to_person=b).first()
        return r.relationship_type if r else None

    def test_biological_parents_typed_from_sex(self):
        u = self._commit("typed1@example.com")
        self.assertEqual(self._rel(u, "Marvin Jenkins", "Danny Jenkins"), "biological father of")
        self.assertEqual(self._rel(u, "Barbara Dorff", "Danny Jenkins"), "biological mother of")

    def test_confident_stepmother_inferred_no_question(self):
        # Overwhelming evidence: Marvin married ONLY Gloria (1980), while Danny (b.1971)
        # was a minor → Gloria is Danny's stepmother, no clarification needed.
        from apps.legacy.models import ImportBatch, Person, Relationship
        from apps.legacy.services import clarification
        from apps.legacy.services.import_engine import _is_parentish
        u = self._commit("typed2@example.com")
        self.assertEqual(self._rel(u, "Gloria Katzell", "Danny Jenkins"), "stepmother of")
        danny = Person.objects.get(user=u, display_name="Danny Jenkins")
        parents = [r for r in Relationship.objects.filter(user=u, to_person=danny)
                   if _is_parentish((r.relationship_type or "").lower())]
        self.assertEqual(len(parents), 3)     # Marvin (bio), Barbara (bio), Gloria (step)
        batch = ImportBatch.objects.filter(user=u, source_type="gedcom").first()
        steps = [c for c in clarification.pending(batch) if c["kind"] == "step_parent"]
        self.assertEqual(steps, [])           # nothing to ask — the evidence was clear

    def test_competing_spouses_go_to_clarification(self):
        # Marvin married TWO women — Legacy cannot tell which is the step-parent → ask,
        # and invent nothing.
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME Marv /J/\n1 SEX M\n"
               "0 @I2@ INDI\n1 NAME Barb /D/\n1 SEX F\n"
               "0 @I3@ INDI\n1 NAME Kid /J/\n1 SEX M\n1 BIRT\n2 DATE 1971\n"
               "0 @I4@ INDI\n1 NAME Glo /K/\n1 SEX F\n"
               "0 @I5@ INDI\n1 NAME Helen /M/\n1 SEX F\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
               "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I4@\n1 MARR\n2 DATE 1980\n"
               "0 @F3@ FAM\n1 HUSB @I1@\n1 WIFE @I5@\n1 MARR\n2 DATE 1990\n0 TRLR\n")
        from apps.legacy.models import ImportBatch
        from apps.legacy.services import clarification
        u = self._commit("compete@example.com", ged=ged)
        self.assertIsNone(self._rel(u, "Glo K", "Kid J"))      # not invented
        self.assertIsNone(self._rel(u, "Helen M", "Kid J"))
        batch = ImportBatch.objects.filter(user=u, source_type="gedcom").first()
        steps = [c for c in clarification.pending(batch) if c["kind"] == "step_parent"]
        self.assertTrue(steps)                                 # asked instead

    def test_unclear_chronology_goes_to_clarification(self):
        # A single spouse but NO marriage year → chronology unclear → ask, don't infer.
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME Marv /J/\n1 SEX M\n"
               "0 @I2@ INDI\n1 NAME Barb /D/\n1 SEX F\n"
               "0 @I3@ INDI\n1 NAME Kid /J/\n1 SEX M\n1 BIRT\n2 DATE 1971\n"
               "0 @I4@ INDI\n1 NAME Glo /K/\n1 SEX F\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
               "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I4@\n1 MARR\n0 TRLR\n")
        from apps.legacy.models import ImportBatch
        from apps.legacy.services import clarification
        u = self._commit("unclear@example.com", ged=ged)
        self.assertIsNone(self._rel(u, "Glo K", "Kid J"))
        batch = ImportBatch.objects.filter(user=u, source_type="gedcom").first()
        ref = next(c["ref"] for c in clarification.pending(batch) if c["kind"] == "step_parent")
        # Resolving to step creates it (teach-once).
        self.assertTrue(clarification.resolve(batch, "step_parent", ref, "step", ""))
        self.assertEqual(self._rel(u, "Glo K", "Kid J"), "stepmother of")
        self.assertEqual([c for c in clarification.pending(batch)
                          if c["kind"] == "step_parent"], [])

    def test_adult_child_at_marriage_is_neither_inferred_nor_asked(self):
        # The child was 40 when the parent remarried — not a meaningful step-parent.
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME Marv /J/\n1 SEX M\n"
               "0 @I2@ INDI\n1 NAME Barb /D/\n1 SEX F\n"
               "0 @I3@ INDI\n1 NAME Kid /J/\n1 SEX M\n1 BIRT\n2 DATE 1950\n"
               "0 @I4@ INDI\n1 NAME Glo /K/\n1 SEX F\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n"
               "0 @F2@ FAM\n1 HUSB @I1@\n1 WIFE @I4@\n1 MARR\n2 DATE 1995\n0 TRLR\n")
        from apps.legacy.models import ImportBatch
        from apps.legacy.services import clarification
        u = self._commit("adult@example.com", ged=ged)
        self.assertIsNone(self._rel(u, "Glo K", "Kid J"))      # not inferred
        batch = ImportBatch.objects.filter(user=u, source_type="gedcom").first()
        self.assertEqual([c for c in clarification.pending(batch)
                          if c["kind"] == "step_parent"], [])   # not asked either

    def test_explicit_step_pedigree_creates_stepparent(self):
        # When the file DOES prove it (_MREL Step), the importer records it directly.
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME Marv /J/\n1 SEX M\n"
               "0 @I2@ INDI\n1 NAME Glo /K/\n1 SEX F\n"
               "0 @I3@ INDI\n1 NAME Kid /J/\n1 SEX M\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n2 _MREL Step\n1 MARR\n2 DATE 1990\n0 TRLR\n")
        u = self._commit("typed_ped@example.com", ged=ged)
        self.assertEqual(self._rel(u, "Glo K", "Kid J"), "stepmother of")   # evidence-based

    def test_adoptive_parents_from_pedigree(self):
        u = self._commit("typed3@example.com")
        self.assertEqual(self._rel(u, "Marvin Jenkins", "Adam Poe"), "adoptive father of")
        self.assertEqual(self._rel(u, "Gloria Katzell", "Adam Poe"), "adoptive mother of")

    def test_person_sex_is_stored(self):
        from apps.legacy.models import Person
        u = self._commit("typed4@example.com")
        self.assertEqual(Person.objects.get(user=u, display_name="Marvin Jenkins").sex, "M")
        self.assertEqual(Person.objects.get(user=u, display_name="Barbara Dorff").sex, "F")

    def test_reimport_upgrades_generic_parent(self):
        # A pre-existing generic 'parent of' is refined in place, never duplicated.
        from apps.legacy.models import Person, Relationship
        from apps.legacy.services.import_engine import refine_existing_family_types
        u = self._commit("typed5@example.com")
        marv = Person.objects.get(user=u, display_name="Marvin Jenkins")
        danny = Person.objects.get(user=u, display_name="Danny Jenkins")
        Relationship.objects.filter(user=u, from_person=marv, to_person=danny).update(
            relationship_type="parent of")
        refine_existing_family_types(u)
        rels = Relationship.objects.filter(user=u, from_person=marv, to_person=danny)
        self.assertEqual(rels.count(), 1)                       # not duplicated
        self.assertEqual(rels.first().relationship_type, "biological father of")


class PreservationLayerTests(TestCase):
    """The permanent preservation layer — facts Canonical Truth can't model yet are
    stored durably (never trapped in one import session), so a future domain
    backfills without any re-import."""

    def _commit(self, email):
        from apps.legacy.services.import_engine import commit_genealogy
        u = _make_user(email)
        batch = create_batch(u, "Tree", "gedcom", RICH, classifier=lambda units: {})
        commit_genealogy(batch)
        return u, batch

    def test_commit_writes_permanent_preserved_facts(self):
        from apps.legacy.models import PreservedFact
        u, batch = self._commit("layer1@example.com")
        pf = PreservedFact.objects.filter(user=u)
        tags = set(pf.values_list("original_tag", flat=True))
        # Every unsupported fact is a durable row — including the custom tag.
        for tag in ("OCCU", "RELI", "BAPM", "RESI", "IMMI", "BURI", "SOUR", "_MILT"):
            self.assertIn(tag, tags)
        # Grouped by concept, tied to the Person, with the raw value kept verbatim.
        occu = pf.get(original_tag="OCCU")
        self.assertEqual(occu.concept, "Career")
        self.assertEqual(occu.value, "Railroad conductor")
        self.assertIsNotNone(occu.person_id)

    def test_supported_facts_are_not_preserved(self):
        from apps.legacy.models import PreservedFact
        u, _ = self._commit("layer2@example.com")
        # BIRT went to Canonical Truth (Person.birth_date), never the holding layer.
        self.assertFalse(PreservedFact.objects.filter(user=u, original_tag="BIRT").exists())

    def test_custom_tag_marked_not_yet_recognized(self):
        from apps.legacy.models import PreservedFact
        u, _ = self._commit("layer3@example.com")
        milt = PreservedFact.objects.get(user=u, original_tag="_MILT")
        self.assertEqual(milt.fact_status, PreservedFact.FactStatus.UNKNOWN)
        self.assertEqual(milt.concept, "Custom Tags")

    def test_preservation_is_idempotent(self):
        from apps.legacy.models import PreservedFact
        from apps.legacy.services.import_engine import commit_genealogy
        u, batch = self._commit("layer4@example.com")
        first = PreservedFact.objects.filter(user=u).count()
        commit_genealogy(batch)                       # re-commit
        self.assertEqual(PreservedFact.objects.filter(user=u).count(), first)

    def test_facts_persist_independently_of_the_import_session(self):
        # The core promise: query preserved facts with no reference to the batch —
        # a future Military domain would read exactly this, no re-import required.
        from apps.legacy.models import PreservedFact
        u, batch = self._commit("layer5@example.com")
        batch.delete()   # even if the batch record is gone, the facts remain
        self.assertTrue(PreservedFact.objects.filter(user=u, concept="Career").exists())

    def test_roadmap_aggregates_by_concept_from_real_data(self):
        from apps.legacy.services.preservation import preservation_roadmap
        u, _ = self._commit("layer6@example.com")
        roadmap = preservation_roadmap(u)
        concepts = {c["concept"]: c for c in roadmap["concepts"]}
        for concept in ("Career", "Faith Journey", "Life Events", "Immigration",
                        "Places", "Sources & Citations", "Custom Tags"):
            self.assertIn(concept, concepts)
        faith = concepts["Faith Journey"]
        self.assertEqual(faith["count"], 2)           # RELI + BAPM
        self.assertTrue(faith["examples"])            # representative examples present
        self.assertEqual(concepts["Custom Tags"]["status"], "unknown")
        self.assertEqual(concepts["Career"]["status"], "awaiting")


# A family record does NOT imply marriage. F1 (Marvin + Barbara, child Danny) has
# NO marriage evidence; F2 (Marvin + Gloria) has a MARR event.
MARR_GED = """0 HEAD
0 @I1@ INDI
1 NAME Marvin Lynn /Jenkins/
0 @I2@ INDI
1 NAME Barbara Jean /Dorff/
0 @I3@ INDI
1 NAME Gloria Ann /Katzell/
0 @I4@ INDI
1 NAME Danny Ray /Jenkins/
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I4@
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I3@
1 MARR
2 DATE 1980
0 TRLR
"""


class MarriageEvidenceTests(TestCase):
    """A GEDCOM FAM is a family UNIT — marriage is only recorded with real evidence."""

    def test_family_without_marriage_event_is_not_married(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @I3@ INDI\n1 NAME C /X/\n0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
               "1 CHIL @I3@\n0 TRLR\n")
        fam = next(c for c in gedcom_parser.parse_gedcom(ged) if c["kind"] == "gedcom_family")
        self.assertIsNone(fam["data"]["couple_type"])

    def test_marr_event_means_married(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 MARR\n2 DATE 1990\n0 TRLR\n")
        fam = next(c for c in gedcom_parser.parse_gedcom(ged) if c["kind"] == "gedcom_family")
        self.assertEqual(fam["data"]["couple_type"], "married")

    def test_divorce_means_former(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 MARR\n2 DATE 1990\n"
               "1 DIV\n2 DATE 2001\n0 TRLR\n")
        fam = next(c for c in gedcom_parser.parse_gedcom(ged) if c["kind"] == "gedcom_family")
        self.assertEqual(fam["data"]["couple_type"], "former")

    def test_commit_does_not_invent_marriage(self):
        from django.db.models import Q
        from apps.legacy.models import Person, Relationship
        from apps.legacy.services.import_engine import commit_genealogy
        u = _make_user("marr@example.com")
        commit_genealogy(create_batch(u, "Tree", "gedcom", MARR_GED, classifier=lambda x: {}))
        p = lambda s: Person.objects.get(user=u, display_name__icontains=s)
        marvin, barbara, gloria, danny = p("Marvin"), p("Barbara"), p("Gloria"), p("Danny")

        def married(a, b):
            return Relationship.objects.filter(
                user=u, relationship_type__icontains="married").filter(
                Q(from_person=a, to_person=b) | Q(from_person=b, to_person=a)).exists()

        # Marvin + Barbara: a family unit, NEVER married (no evidence).
        self.assertFalse(married(marvin, barbara))
        # Marvin + Gloria: MARR event ⇒ married.
        self.assertTrue(married(marvin, gloria))
        # Both are still biological parents of Danny.
        self.assertTrue(Relationship.objects.filter(
            user=u, from_person=marvin, to_person=danny, relationship_type__icontains="parent").exists())
        self.assertTrue(Relationship.objects.filter(
            user=u, from_person=barbara, to_person=danny, relationship_type__icontains="parent").exists())


class MarriageRepairMigrationTests(TestCase):
    """The data migration removes marriages the old importer inferred, keeps real ones."""

    def test_repair_removes_only_inferred_marriages(self):
        import importlib
        from django.apps import apps as django_apps
        from django.db.models import Q
        from apps.legacy.models import Person, Relationship, ImportBatch, ImportChunk

        u = _make_user("repairmig@example.com")
        batch = ImportBatch.objects.create(user=u, source_name="t", source_type="gedcom")

        def person(name, xref):
            return Person.objects.create(user=u, display_name=name,
                                         source_batch=batch, gedcom_xref=xref)
        marvin, barbara, gloria = person("Marvin", "@I1@"), person("Barbara", "@I2@"), person("Gloria", "@I3@")
        # Legacy chunks (no couple_type key) — F1 has NO marriage fields, F2 does.
        ImportChunk.objects.create(batch=batch, index=1, chunk_kind="gedcom_family",
            data={"husb": "@I1@", "wife": "@I2@", "marriage_year": None, "marriage_place": ""})
        ImportChunk.objects.create(batch=batch, index=2, chunk_kind="gedcom_family",
            data={"husb": "@I1@", "wife": "@I3@", "marriage_year": 1980, "marriage_place": ""})
        # Both marriages as the old importer created them.
        Relationship.objects.create(user=u, from_person=marvin, to_person=barbara, relationship_type="married to")
        Relationship.objects.create(user=u, from_person=marvin, to_person=gloria, relationship_type="married to")

        mod = importlib.import_module("apps.legacy.migrations.0025_repair_inferred_marriages")
        mod.repair(django_apps, None)

        def married(a, b):
            return Relationship.objects.filter(relationship_type__icontains="married").filter(
                Q(from_person=a, to_person=b) | Q(from_person=b, to_person=a)).exists()
        self.assertFalse(married(marvin, barbara))   # inferred (no evidence) → removed
        self.assertTrue(married(marvin, gloria))     # real (marriage year) → kept


# A lasting family unit (three shared children) with NO marriage event — the
# needs-clarification case. Legacy asks the user; it never asserts a marriage.
LIKELY_GED = """0 HEAD
0 @I1@ INDI
1 NAME Marvin Lynn /Jenkins/
0 @I2@ INDI
1 NAME Barbara Jean /Dorff/
0 @I3@ INDI
1 NAME Danny Ray /Jenkins/
0 @I4@ INDI
1 NAME Julie Mae /Jenkins/
0 @I5@ INDI
1 NAME Lynne Anne /Jenkins/
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
1 CHIL @I5@
0 TRLR
"""


class MarriageStatusTests(TestCase):
    """Known vs Needs-Clarification — the importer preserves evidence, never infers."""

    def _fam(self, ged):
        return next(c for c in gedcom_parser.parse_gedcom(ged) if c["kind"] == "gedcom_family")

    def test_multiple_children_no_marriage_needs_clarification(self):
        fam = self._fam(LIKELY_GED)
        # NOT inferred as married — couple_type stays None, only a question is raised.
        self.assertIsNone(fam["data"]["couple_type"])
        self.assertEqual(fam["data"]["marriage_status"], "needs_clarification")

    def test_single_child_no_marriage_raises_no_question(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @I3@ INDI\n1 NAME C /X/\n0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n"
               "1 CHIL @I3@\n0 TRLR\n")
        fam = self._fam(ged)
        self.assertIsNone(fam["data"]["couple_type"])
        self.assertIsNone(fam["data"]["marriage_status"])

    def test_marr_is_known(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 MARR\n2 DATE 1990\n0 TRLR\n")
        fam = self._fam(ged)
        self.assertEqual(fam["data"]["couple_type"], "married")
        self.assertEqual(fam["data"]["marriage_status"], "known")


class ClarificationEngineTests(TestCase):
    """Incomplete marriage evidence becomes a QUESTION; the user resolves it, and only
    then does it enter Canonical Truth. The importer never asserts a marriage."""

    def setUp(self):
        from apps.legacy.services.import_engine import commit_genealogy
        self.user = _make_user("clarify@example.com")
        self.batch = create_batch(self.user, "Tree", "gedcom", LIKELY_GED, classifier=lambda x: {})
        commit_genealogy(self.batch)

    def _pair(self):
        from apps.legacy.models import Person
        return (Person.objects.get(user=self.user, display_name__icontains="Marvin"),
                Person.objects.get(user=self.user, display_name__icontains="Barbara"))

    def _married(self, a, b):
        from django.db.models import Q
        from apps.legacy.models import Relationship
        return Relationship.objects.filter(user=self.user, relationship_type__icontains="married").filter(
            Q(from_person=a, to_person=b) | Q(from_person=b, to_person=a)).exists()

    def _q(self):
        from apps.legacy.services import clarification
        return clarification.pending(self.batch)

    def test_gap_is_a_non_leading_question_with_evidence(self):
        marvin, barbara = self._pair()
        self.assertFalse(self._married(marvin, barbara))          # NOTHING asserted
        q = self._q()
        self.assertEqual(len(q), 1)
        item = q[0]
        self.assertEqual(item["kind"], "marriage_status")
        # Non-leading: the prompt must not suggest an answer ("married").
        self.assertNotIn("married", item["prompt"].lower())
        self.assertEqual(item["prompt"], "How should Legacy represent this relationship?")
        # Evidence explains WHY Legacy is asking (both people, the counts, the source).
        ev = {(e["label"], e["value"]) for e in item["evidence"]}
        self.assertIn(("Person", "Marvin Lynn Jenkins"), ev)
        self.assertIn(("Person", "Barbara Jean Dorff"), ev)
        self.assertIn(("Shared children", "3"), ev)
        self.assertIn(("Marriage record", "None in the imported file"), ev)
        # Neutral options incl. free-text Other.
        vals = {o["value"] for o in item["options"]}
        self.assertEqual(vals, {"married", "former", "never", "partner"})
        self.assertTrue(item["allow_other"])

    def test_dispatch_by_kind_and_answer_married(self):
        from apps.legacy.services import clarification
        marvin, barbara = self._pair()
        item = self._q()[0]
        self.assertTrue(clarification.resolve(self.batch, item["kind"], item["ref"], "married"))
        self.assertTrue(self._married(marvin, barbara))           # now in Canonical Truth
        self.assertEqual(self._q(), [])                           # never asked again

    def test_answer_never_keeps_co_parents(self):
        from apps.legacy.services import clarification
        marvin, barbara = self._pair()
        item = self._q()[0]
        clarification.resolve(self.batch, item["kind"], item["ref"], "never")
        self.assertFalse(self._married(marvin, barbara))          # co-parents only
        self.assertEqual(self._q(), [])                           # not asked again

    def test_answer_partner_records_domestic_partner(self):
        from apps.legacy.models import Relationship
        from apps.legacy.services import clarification
        marvin, barbara = self._pair()
        item = self._q()[0]
        clarification.resolve(self.batch, item["kind"], item["ref"], "partner")
        self.assertTrue(Relationship.objects.filter(
            user=self.user, from_person=marvin, to_person=barbara,
            relationship_type="domestic partner of").exists())
        self.assertEqual(self._q(), [])

    def test_answer_other_uses_free_text(self):
        from apps.legacy.models import Relationship
        from apps.legacy.services import clarification
        marvin, barbara = self._pair()
        item = self._q()[0]
        clarification.resolve(self.batch, item["kind"], item["ref"], "other", "engaged to")
        self.assertTrue(Relationship.objects.filter(
            user=self.user, from_person=marvin, to_person=barbara,
            relationship_type="engaged to").exists())
        self.assertEqual(self._q(), [])

    def test_unknown_kind_is_ignored(self):
        from apps.legacy.services import clarification
        item = self._q()[0]
        self.assertFalse(clarification.resolve(self.batch, "not_a_type", item["ref"], "married"))
        self.assertEqual(len(self._q()), 1)                       # still open
