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
