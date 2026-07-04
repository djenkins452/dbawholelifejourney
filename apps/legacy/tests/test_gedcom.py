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
