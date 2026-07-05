"""Smart Refresh — synchronize an existing import; never duplicate, never erode."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.legacy.models import ImportBatch, Person, PreservedFact, Relationship
from apps.legacy.services import refresh as refresh_svc
from apps.legacy.services.import_engine import commit_genealogy, create_batch

User = get_user_model()


def _u(email="refresh@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


# v1: Marvin (M) + Barbara (F) → Danny. No dates.
GED_V1 = """0 HEAD
0 @I1@ INDI
1 NAME Marvin /Jenkins/
1 SEX M
0 @I2@ INDI
1 NAME Barbara /Dorff/
1 SEX F
0 @I3@ INDI
1 NAME Danny /Jenkins/
1 SEX M
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
0 TRLR
"""

# v2 of the SAME tree: adds Danny's birth date, a new child Julie (@I4@), and an
# occupation fact — a richer, newer export of the same source.
GED_V2 = """0 HEAD
0 @I1@ INDI
1 NAME Marvin /Jenkins/
1 SEX M
1 OCCU Railroad conductor
0 @I2@ INDI
1 NAME Barbara /Dorff/
1 SEX F
0 @I3@ INDI
1 NAME Danny /Jenkins/
1 SEX M
1 BIRT
2 DATE 29 MAR 1971
0 @I4@ INDI
1 NAME Julie /Jenkins/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I4@
0 TRLR
"""

# A totally different family — must NOT be seen as the same source.
GED_OTHER = """0 HEAD
0 @I1@ INDI
1 NAME Walter /Poe/
1 SEX M
0 @I2@ INDI
1 NAME Rose /Kade/
1 SEX F
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
0 TRLR
"""


class DetectionTests(TestCase):
    def setUp(self):
        self.u = _u()
        self.original = create_batch(self.u, "Family v1", "gedcom", GED_V1, classifier=lambda x: {})
        commit_genealogy(self.original)

    def test_recognizes_the_same_source(self):
        incoming = create_batch(self.u, "Family v2", "gedcom", GED_V2, classifier=lambda x: {})
        self.assertEqual(refresh_svc.detect_existing_source(self.u, incoming), self.original)

    def test_does_not_confuse_a_different_family(self):
        other = create_batch(self.u, "Other", "gedcom", GED_OTHER, classifier=lambda x: {})
        self.assertIsNone(refresh_svc.detect_existing_source(self.u, other))


class RefreshApplyTests(TestCase):
    def setUp(self):
        self.u = _u()
        self.original = create_batch(self.u, "Family v1", "gedcom", GED_V1, classifier=lambda x: {})
        commit_genealogy(self.original)
        self.incoming = create_batch(self.u, "Family v2", "gedcom", GED_V2, classifier=lambda x: {})

    def _person(self, name):
        return Person.objects.get(user=self.u, display_name=name)

    def test_refresh_synchronizes_without_duplicating(self):
        before = Person.objects.filter(user=self.u).count()   # 3
        audit = refresh_svc.apply_refresh(self.original, self.incoming)
        after = Person.objects.filter(user=self.u).count()
        # Exactly one NEW person (Julie); the other three matched, not duplicated.
        self.assertEqual(after, before + 1)
        self.assertEqual(audit["people_added"], 1)
        self.assertEqual(Person.objects.filter(user=self.u, display_name="Danny Jenkins").count(), 1)
        self.assertEqual(Person.objects.filter(user=self.u, display_name="Marvin Jenkins").count(), 1)
        self.assertTrue(Person.objects.filter(user=self.u, display_name="Julie Jenkins").exists())

    def test_refresh_improves_facts_from_richer_source(self):
        self.assertIsNone(self._person("Danny Jenkins").birth_date)
        refresh_svc.apply_refresh(self.original, self.incoming)
        self.assertEqual(str(self._person("Danny Jenkins").birth_date), "1971-03-29")

    def test_refresh_never_overwrites_user_edits(self):
        # User corrected Marvin's bond and it must survive a refresh from a poorer file.
        marv, danny = self._person("Marvin Jenkins"), self._person("Danny Jenkins")
        rel = Relationship.objects.get(user=self.u, from_person=marv, to_person=danny)
        rel.relationship_type = "adoptive father of"
        rel.user_edited = True
        rel.save()
        refresh_svc.apply_refresh(self.original, self.incoming)
        rel.refresh_from_db()
        self.assertEqual(rel.relationship_type, "adoptive father of")   # NOT reverted

    def test_refresh_preserves_new_unsupported_facts(self):
        before = PreservedFact.objects.filter(user=self.u).count()
        audit = refresh_svc.apply_refresh(self.original, self.incoming)
        self.assertGreater(PreservedFact.objects.filter(user=self.u).count(), before)
        self.assertGreaterEqual(audit["facts_preserved"], 1)   # Marvin's occupation

    def test_refresh_is_idempotent(self):
        refresh_svc.apply_refresh(self.original, self.incoming)
        n_people = Person.objects.filter(user=self.u).count()
        n_rels = Relationship.objects.filter(user=self.u).count()
        again = create_batch(self.u, "Family v2 again", "gedcom", GED_V2, classifier=lambda x: {})
        refresh_svc.apply_refresh(self.original, again)
        self.assertEqual(Person.objects.filter(user=self.u).count(), n_people)
        self.assertEqual(Relationship.objects.filter(user=self.u).count(), n_rels)

    def test_audit_is_recorded_permanently(self):
        refresh_svc.apply_refresh(self.original, self.incoming)
        self.incoming.refresh_from_db()
        self.assertTrue(self.incoming.is_refresh)
        self.assertEqual(self.incoming.refresh_of_id, self.original.pk)
        self.assertIn("duplicates_prevented", self.incoming.refresh_summary)
