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
