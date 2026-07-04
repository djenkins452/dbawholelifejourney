"""Full dates (Deployment 4) — preserve GEDCOM exact dates, show '29 Mar 1971'."""

import datetime
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.legacy.models import Person
from apps.legacy.services import gedcom_parser
from apps.legacy.services.import_engine import commit_genealogy, create_batch
from apps.legacy.tests.test_gedcom import SAMPLE

User = get_user_model()


def _make_user(email="keeper@example.com"):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _boom(units):
    raise AssertionError("classifier must not run for GEDCOM")


class FullDateParseTests(TestCase):
    def test_full_date_only_when_day_present(self):
        self.assertEqual(gedcom_parser._full_date("29 MAR 1971"), "1971-03-29")
        self.assertEqual(gedcom_parser._full_date("3 MAR 1945"), "1945-03-03")
        self.assertIsNone(gedcom_parser._full_date("MAR 1971"))   # month-only
        self.assertIsNone(gedcom_parser._full_date("1971"))        # year-only
        self.assertIsNone(gedcom_parser._full_date("ABT 1945"))    # approximate
        self.assertIsNone(gedcom_parser._full_date("31 FEB 1970")) # invalid → None

    def test_parser_stores_full_and_year(self):
        chunks = gedcom_parser.parse_gedcom(SAMPLE)
        marvin = next(c for c in chunks if c["title"] == "Marvin Jenkins")["data"]
        self.assertEqual(marvin["birth_date"], "1945-03-03")
        self.assertEqual(marvin["death_date"], "2010-12-12")
        self.assertEqual(marvin["birth_year"], 1945)
        betty = next(c for c in chunks if c["title"] == "Betty Jenkins")["data"]
        self.assertIsNone(betty["birth_date"])     # GEDCOM had year only
        self.assertEqual(betty["birth_year"], 1948)


class FullDateCommitTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_commit_sets_full_dates(self):
        commit_genealogy(create_batch(self.user, "Tree", "gedcom", SAMPLE, classifier=_boom))
        marvin = Person.objects.get(user=self.user, display_name="Marvin Jenkins")
        self.assertEqual(marvin.birth_date, datetime.date(1945, 3, 3))
        self.assertEqual(marvin.death_date, datetime.date(2010, 12, 12))
        self.assertEqual(marvin.display_birth, "3 Mar 1945")     # exact day shown
        betty = Person.objects.get(user=self.user, display_name="Betty Jenkins")
        self.assertIsNone(betty.birth_date)
        self.assertEqual(betty.display_birth, "1948")            # year-only fallback

    def test_marriage_full_date(self):
        ged = ("0 HEAD\n0 @I1@ INDI\n1 NAME A /X/\n0 @I2@ INDI\n1 NAME B /Y/\n"
               "0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 MARR\n2 DATE 7 JUN 1997\n0 TRLR\n")
        commit_genealogy(create_batch(self.user, "T", "gedcom", ged, classifier=_boom))
        from apps.legacy.models import Relationship
        rel = Relationship.objects.get(user=self.user, relationship_type="married to")
        self.assertEqual(rel.started_date, datetime.date(1997, 6, 7))
        self.assertEqual(rel.started_year, 1997)
        self.assertEqual(rel.display_started, "7 Jun 1997")


class DisplayTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_display_prefers_full_date(self):
        p = Person.objects.create(user=self.user, display_name="X",
                                  birth_year=1971, birth_date=datetime.date(1971, 3, 29))
        self.assertEqual(p.display_birth, "29 Mar 1971")

    def test_display_falls_back_to_year(self):
        p = Person.objects.create(user=self.user, display_name="Y", birth_year=1971)
        self.assertEqual(p.display_birth, "1971")

    def test_display_empty_when_unknown(self):
        p = Person.objects.create(user=self.user, display_name="Z")
        self.assertEqual(p.display_birth, "")


class BackfillTests(TestCase):
    def setUp(self):
        self.user = _make_user()

    def test_dates_from_body(self):
        b, d = gedcom_parser.dates_from_body(
            "Male · Born 3 MAR 1945 in Knoxville, Tennessee · Died 12 DEC 2010 in Maryville")
        self.assertEqual(b, "1945-03-03")
        self.assertEqual(d, "2010-12-12")

    def test_commit_recovers_dates_from_body(self):
        # Simulate a pre-date-capture import: chunks whose structured data lacks
        # dates but whose body still reads "Born 3 MAR 1945".
        batch = create_batch(self.user, "T", "gedcom", SAMPLE, classifier=_boom)
        for ch in batch.chunks.filter(chunk_kind="gedcom_person"):
            ch.data.pop("birth_date", None); ch.data.pop("death_date", None)
            ch.save(update_fields=["data"])
        commit_genealogy(batch)
        marvin = Person.objects.get(user=self.user, display_name="Marvin Jenkins")
        self.assertEqual(marvin.birth_date, datetime.date(1945, 3, 3))    # recovered from body

    def test_backfill_fills_existing_people(self):
        from apps.legacy.services import import_engine
        batch = create_batch(self.user, "T", "gedcom", SAMPLE, classifier=_boom)
        commit_genealogy(batch)
        Person.objects.filter(user=self.user).update(birth_date=None, death_date=None)  # old state
        updated = import_engine.backfill_gedcom_dates(self.user)
        self.assertGreater(updated, 0)
        marvin = Person.objects.get(user=self.user, display_name="Marvin Jenkins")
        self.assertEqual(marvin.birth_date, datetime.date(1945, 3, 3))
        self.assertEqual(marvin.display_birth, "3 Mar 1945")
