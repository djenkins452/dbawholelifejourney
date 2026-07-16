"""Preservation-safe canonical merge + conservative reconciliation bridge."""

from django.test import TestCase

from apps.people.models import (
    Person, PersonEvent, PersonMembership, PersonOrigin, PersonPhoto,
    PersonSourceLink, RecognitionPhrase,
)
from apps.people.services import hooks, membership, phrases, reconciliation
from apps.people.services.merge import merge_persons

from ._helpers import make_user


class MergeTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.winner = Person.objects.create(user=self.user, first_name="Marvin", last_name="Lynn Jenkins")
        self.loser = Person.objects.create(user=self.user, first_name="Marvin", last_name="Jenkins")

    def tearDown(self):
        hooks._reset_for_tests()

    def test_merge_soft_deletes_loser_not_hard(self):
        merge_persons(self.user, self.loser, self.winner)
        # Gone from active queries, but preserved (reversible) — NOT hard-deleted.
        self.assertFalse(Person.objects.filter(pk=self.loser.pk).exists())
        self.assertTrue(Person.all_objects.filter(pk=self.loser.pk).exists())
        self.loser.refresh_from_db()
        self.assertEqual(self.loser.status, "deleted")

    def test_membership_follows_survivor(self):
        membership.grant_membership(self.loser, PersonMembership.Grant.MANUAL)
        merge_persons(self.user, self.loser, self.winner)
        self.assertTrue(membership.is_member(self.winner))

    def test_phrases_photos_events_repoint(self):
        phrases.add_custom_phrase(self.loser, "Pa")
        PersonPhoto.objects.create(person=self.loser, image="people/photos/x.jpg", is_primary=True)
        merge_persons(self.user, self.loser, self.winner)
        self.assertTrue(RecognitionPhrase.objects.filter(person=self.winner, normalized="pa").exists())
        self.assertTrue(PersonPhoto.objects.filter(person=self.winner).exists())
        self.assertTrue(PersonEvent.objects.filter(
            person=self.winner, event_type=PersonEvent.Type.MERGE_COMPLETED).exists())

    def test_source_links_repoint(self):
        PersonSourceLink.objects.create(person=self.loser, source_domain="legacy", source_pk=99)
        merge_persons(self.user, self.loser, self.winner)
        link = PersonSourceLink.objects.get(source_domain="legacy", source_pk=99)
        self.assertEqual(link.person_id, self.winner.pk)

    def test_loser_name_stays_resolvable(self):
        merge_persons(self.user, self.loser, self.winner)
        rp = RecognitionPhrase.objects.filter(person=self.winner, normalized="marvin jenkins").first()
        self.assertIsNotNone(rp)
        self.assertEqual(rp.source, RecognitionPhrase.Source.LEARNED)

    def test_deceased_and_self_are_or_merged(self):
        self.loser.is_deceased = True; self.loser.save()
        merge_persons(self.user, self.loser, self.winner)
        self.winner.refresh_from_db()
        self.assertTrue(self.winner.is_deceased)

    def test_feature_merge_participant_is_invoked(self):
        calls = []
        hooks.register_merge_participant(lambda u, l, w: calls.append((l.pk, w.pk)))
        merge_persons(self.user, self.loser, self.winner)
        self.assertEqual(calls, [(self.loser.pk, self.winner.pk)])

    def test_cannot_merge_into_self(self):
        with self.assertRaises(ValueError):
            merge_persons(self.user, self.winner, self.winner)


class ReconciliationTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_new_source_row_creates_person_and_link(self):
        person, outcome = reconciliation.ingest_source_person(
            self.user, source_domain="relationships", source_pk=1,
            display_name="Heather Jenkins", origin=PersonOrigin.CONTACT_IMPORT)
        self.assertEqual(outcome, reconciliation.CREATED)
        self.assertTrue(PersonSourceLink.objects.filter(
            source_domain="relationships", source_pk=1, person=person).exists())

    def test_ingest_is_idempotent(self):
        p1, _ = reconciliation.ingest_source_person(
            self.user, source_domain="relationships", source_pk=1, display_name="Heather Jenkins")
        p2, outcome = reconciliation.ingest_source_person(
            self.user, source_domain="relationships", source_pk=1, display_name="Heather Jenkins")
        self.assertEqual(p1.pk, p2.pk)
        self.assertEqual(outcome, reconciliation.ALREADY_LINKED)

    def test_exact_match_links_not_duplicates(self):
        existing = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        person, outcome = reconciliation.ingest_source_person(
            self.user, source_domain="legacy", source_pk=5, display_name="Heather Jenkins",
            email="h@example.com")
        self.assertEqual(outcome, reconciliation.LINKED)
        self.assertEqual(person.pk, existing.pk)
        person.refresh_from_db()
        self.assertEqual(person.email, "h@example.com")   # blank filled, never overwritten

    def test_ambiguous_match_routes_to_review_never_guesses(self):
        Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        Person.objects.create(user=self.user, display_name="Heather Jenkins")  # 2nd same name
        person, outcome = reconciliation.ingest_source_person(
            self.user, source_domain="legacy", source_pk=7, display_name="Heather Jenkins")
        self.assertEqual(outcome, reconciliation.REVIEW)
        self.assertTrue(PersonEvent.objects.filter(
            person=person, event_type=PersonEvent.Type.DUPLICATE_DETECTED).exists())

    def test_membership_granted_when_requested(self):
        person, _ = reconciliation.ingest_source_person(
            self.user, source_domain="relationships", source_pk=1, display_name="Heather",
            membership_via=PersonMembership.Grant.CONTACT_IMPORT)
        self.assertTrue(membership.is_member(person))
