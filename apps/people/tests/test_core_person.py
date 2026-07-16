"""Canonical Person: identity, membership, phrases, provenance."""

from django.test import TestCase

from apps.people.models import (
    Person, PersonEvent, PersonMembership, PersonOrigin, RecognitionPhrase,
)
from apps.people.services import identity, membership, phrases
from apps.people.services.provenance import record_person_event

from ._helpers import make_user


class PersonModelTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_display_name_derived_from_parts(self):
        p = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        self.assertEqual(p.display_name, "Heather Jenkins")

    def test_full_name_and_normalized(self):
        p = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")
        self.assertEqual(p.full_name, "Heather Jenkins")
        self.assertEqual(p.normalized_name, "heather jenkins")

    def test_notes_are_sanitized_with_plain_shadow(self):
        p = Person.objects.create(
            user=self.user, display_name="Heather",
            notes="<p>Loves <script>alert(1)</script>hiking</p>")
        p.refresh_from_db()
        self.assertNotIn("<script>", p.notes)
        self.assertIn("hiking", p.notes_plain)


class IdentityServiceTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_create_person_records_lifecycle_event(self):
        p = identity.create_person(self.user, origin=PersonOrigin.MANUAL, display_name="Heather")
        self.assertTrue(PersonEvent.objects.filter(
            person=p, event_type=PersonEvent.Type.CREATED_MANUAL).exists())

    def test_gedcom_origin_records_import_event(self):
        p = identity.create_person(self.user, origin=PersonOrigin.GEDCOM, display_name="Ancestor")
        self.assertTrue(PersonEvent.objects.filter(
            person=p, event_type=PersonEvent.Type.IMPORTED_GEDCOM).exists())

    def test_self_anchor_is_unique(self):
        a = identity.create_person(self.user, display_name="Me")
        b = identity.create_person(self.user, display_name="Me Again")
        identity.set_self_person(a)
        identity.set_self_person(b)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertFalse(a.is_self)
        self.assertTrue(b.is_self)
        self.assertEqual(identity.get_self_person(self.user).pk, b.pk)


class MembershipTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_grant_is_idempotent_and_never_revoked(self):
        p = Person.objects.create(user=self.user, display_name="Heather")
        m1 = membership.grant_membership(p, PersonMembership.Grant.MANUAL)
        m2 = membership.grant_membership(p, PersonMembership.Grant.MENTION)  # second path
        self.assertEqual(m1.pk, m2.pk)                       # idempotent
        self.assertEqual(m2.granted_via, PersonMembership.Grant.MANUAL)  # original kept
        self.assertTrue(membership.is_member(p))

    def test_members_excludes_non_members(self):
        member = Person.objects.create(user=self.user, display_name="Heather")
        ancestor = Person.objects.create(user=self.user, display_name="6th-gen Ancestor",
                                         origin=PersonOrigin.GEDCOM)
        membership.grant_membership(member, PersonMembership.Grant.MANUAL)
        members = list(membership.members(self.user))
        self.assertIn(member, members)
        self.assertNotIn(ancestor, members)      # GEDCOM-only person is NOT a member

    def test_deceased_member_stays_a_member(self):
        p = Person.objects.create(user=self.user, display_name="Grandma", is_deceased=True)
        membership.grant_membership(p, PersonMembership.Grant.MANUAL)
        self.assertIn(p, list(membership.members(self.user)))


class RecognitionPhraseTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.p = Person.objects.create(user=self.user, first_name="Heather", last_name="Jenkins")

    def test_derived_phrases_include_names_and_compact(self):
        derived = phrases.derived_phrases(self.p)
        self.assertIn("heather jenkins", derived)
        self.assertIn("heather", derived)
        self.assertIn("heatherjenkins", derived)   # @HeatherJenkins compact form

    def test_custom_phrase_stored_and_event_recorded(self):
        rp = phrases.add_custom_phrase(self.p, "Honey")
        self.assertEqual(rp.source, RecognitionPhrase.Source.CUSTOM)
        self.assertEqual(rp.normalized, "honey")
        self.assertTrue(PersonEvent.objects.filter(
            person=self.p, event_type=PersonEvent.Type.PHRASE_CONFIRMED).exists())

    def test_learned_phrase_requires_confirmation_path(self):
        rp = phrases.confirm_learned_phrase(self.p, "Better Half", learned_from="journal:5")
        self.assertEqual(rp.source, RecognitionPhrase.Source.LEARNED)
        self.assertEqual(rp.learned_from, "journal:5")

    def test_phrase_dedupes_per_person(self):
        phrases.add_custom_phrase(self.p, "Honey")
        phrases.add_custom_phrase(self.p, "honey")   # same normalized
        self.assertEqual(
            RecognitionPhrase.objects.filter(person=self.p, normalized="honey").count(), 1)

    def test_remove_phrase_records_event(self):
        phrases.add_custom_phrase(self.p, "Honey")
        removed = phrases.remove_phrase(self.p, "Honey")
        self.assertTrue(removed)
        self.assertFalse(RecognitionPhrase.objects.filter(person=self.p, normalized="honey").exists())
        self.assertTrue(PersonEvent.objects.filter(
            person=self.p, event_type=PersonEvent.Type.PHRASE_REMOVED).exists())


class ProvenanceBoundednessTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_event_detail_is_small_facts(self):
        p = Person.objects.create(user=self.user, display_name="Heather")
        ev = record_person_event(p, PersonEvent.Type.SOURCE_ADDED, source_domain="legacy", source_pk=7)
        self.assertEqual(ev.detail, {"source_domain": "legacy", "source_pk": 7})
        self.assertEqual(ev.actor, "system")
