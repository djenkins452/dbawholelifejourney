"""Phase 0c-B — legacy genealogy backfill (create-distinct, never merge by name).

Gates: every legacy person represented canonically with provenance; same-name
individuals stay SEPARATE (no wrong merges); no cross-merge with living people; no
People membership; aliases → RecognitionPhrase(custom); idempotent; genealogy never
collides with a living person on a bare first name.
"""
from django.test import TestCase

from apps.legacy.models import Person as PersonB, RelationshipAlias
from apps.people.models import (
    Person, PersonEvent, PersonMembership, PersonSourceLink, RecognitionPhrase,
)
from apps.people.services import resolution
from apps.people.services.backfill import backfill_legacy_genealogy

from ._helpers import make_user


class LegacyGenealogyBackfillTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def _run(self):
        return backfill_legacy_genealogy(PersonB, RelationshipAlias)

    def test_legacy_person_becomes_canonical_distinct_with_provenance(self):
        b = PersonB.objects.create(user=self.user, display_name="Ada Lovelace",
                                   gedcom_xref="@I5@", birth_year=1815, death_year=1852)
        self._run()
        link = PersonSourceLink.objects.get(source_domain="legacy", source_pk=b.pk)
        p = link.person
        self.assertEqual(p.display_name, "Ada Lovelace")
        self.assertTrue(p.is_deceased)                  # derived from death_year
        self.assertEqual(p.origin, "gedcom")            # has gedcom_xref
        # No People membership for genealogy.
        self.assertFalse(PersonMembership.objects.filter(person=p).exists())
        self.assertTrue(PersonEvent.objects.filter(person=p).exists())

    def test_same_name_ancestors_never_merge(self):
        b1 = PersonB.objects.create(user=self.user, display_name="William Jenkins",
                                    gedcom_xref="@I1@", birth_year=1880)
        b2 = PersonB.objects.create(user=self.user, display_name="William Jenkins",
                                    gedcom_xref="@I2@", birth_year=1850)  # grandfather
        self._run()
        # Two distinct canonical people, two distinct source links — NEVER merged.
        p1 = PersonSourceLink.objects.get(source_domain="legacy", source_pk=b1.pk).person
        p2 = PersonSourceLink.objects.get(source_domain="legacy", source_pk=b2.pk).person
        self.assertNotEqual(p1.pk, p2.pk)
        self.assertEqual(Person.all_objects.filter(user=self.user, display_name="William Jenkins").count(), 2)

    def test_does_not_collide_with_living_person_on_first_name(self):
        # A living canonical "Heather" (first_name set, e.g. from 0c-A).
        living = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        # A genealogy "Heather Jenkins" (deceased ancestor).
        PersonB.objects.create(user=self.user, display_name="Heather Jenkins",
                               gedcom_xref="@I9@", death_year=1900)
        self._run()
        self.assertEqual(Person.objects.filter(user=self.user).count(), 2)  # distinct
        # resolve("Heather") (bare first name) returns the LIVING person only — the
        # genealogy record has no first_name so it never matches a bare first name.
        r = resolution.resolve(self.user, "Heather")
        self.assertEqual(r.status, "resolved")
        self.assertEqual(r.person.pk, living.pk)

    def test_aliases_migrate_to_custom_recognition_phrases(self):
        b = PersonB.objects.create(user=self.user, display_name="Marvin Jenkins",
                                   also_known_as="Marv, Pops")
        RelationshipAlias.objects.create(user=self.user, alias="dad", label="Dad", person=b)
        self._run()
        p = PersonSourceLink.objects.get(source_domain="legacy", source_pk=b.pk).person
        norms = set(RecognitionPhrase.objects.filter(person=p).values_list("normalized", flat=True))
        self.assertTrue({"marv", "pops", "dad"}.issubset(norms))
        for rp in RecognitionPhrase.objects.filter(person=p):
            self.assertEqual(rp.source, RecognitionPhrase.Source.CUSTOM)

    def test_rerun_is_idempotent(self):
        b = PersonB.objects.create(user=self.user, display_name="Grace Hopper",
                                   also_known_as="Amazing Grace")
        self._run()
        n_people, n_links, n_phrases = (
            Person.objects.count(), PersonSourceLink.objects.count(),
            RecognitionPhrase.objects.count())
        result2 = self._run()
        self.assertEqual(Person.objects.count(), n_people)
        self.assertEqual(PersonSourceLink.objects.count(), n_links)
        self.assertEqual(RecognitionPhrase.objects.count(), n_phrases)
        self.assertEqual(result2["already_linked"], 1)

    def test_soft_deleted_legacy_person_skipped(self):
        PersonB.objects.create(user=self.user, display_name="Removed Ancestor", status="deleted")
        self._run()
        self.assertEqual(Person.objects.filter(user=self.user).count(), 0)
