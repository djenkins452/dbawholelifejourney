"""Phase 0c-A — living-people backfill (relationships A + ai_relationships C).

Local prod-data is empty, so correctness is proven on synthetic legacy rows: the
migration's logic lives in `people.services.backfill`, which these tests drive directly
with the REAL source models. Gates: canonical people created, source links correct,
A+C unified (never guess), ambiguous → review, re-run idempotent, provenance + membership.
"""
from django.test import TestCase

from apps.core.ai_relationships.models import Person as PersonC
from apps.people.models import (
    Person, PersonEvent, PersonMembership, PersonSourceLink,
)
from apps.people.services.backfill import backfill_living_people
from apps.relationships.models import Person as PersonA

from ._helpers import make_user


class LivingBackfillTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user("other@example.com")

    def _run(self):
        return backfill_living_people(PersonA, PersonC)

    # ── A → canonical ───────────────────────────────────────────────────────
    def test_relationships_person_becomes_canonical_with_source_link(self):
        a = PersonA.objects.create(owner=self.user, first_name="Marvin", last_name="Jenkins",
                                   email="m@example.com")
        self._run()
        link = PersonSourceLink.objects.get(source_domain="relationships", source_pk=a.pk)
        p = link.person
        self.assertEqual(p.user_id, self.user.id)
        self.assertEqual(p.first_name, "Marvin")
        self.assertEqual(p.email, "m@example.com")
        # membership + provenance
        self.assertTrue(PersonMembership.objects.filter(person=p).exists())
        self.assertTrue(PersonEvent.objects.filter(person=p).exists())

    # ── A + C unify (the Heather case) ──────────────────────────────────────
    def test_bare_first_name_extraction_unifies_with_full_name_contact(self):
        a = PersonA.objects.create(owner=self.user, first_name="Heather", last_name="Jenkins")
        c = PersonC.objects.create(user=self.user, display_name="Heather")  # bare extraction
        self._run()
        # ONE canonical Heather, TWO source links.
        heathers = Person.objects.filter(user=self.user, first_name="Heather")
        self.assertEqual(heathers.count(), 1)
        p = heathers.first()
        domains = set(PersonSourceLink.objects.filter(person=p).values_list("source_domain", flat=True))
        self.assertEqual(domains, {"relationships", "ai_relationships"})
        self.assertEqual(PersonSourceLink.objects.get(source_domain="ai_relationships", source_pk=c.pk).person_id, p.pk)

    def test_full_name_extraction_also_unifies(self):
        PersonA.objects.create(owner=self.user, first_name="Heather", last_name="Jenkins")
        PersonC.objects.create(user=self.user, display_name="Heather Jenkins")
        self._run()
        self.assertEqual(Person.objects.filter(user=self.user).count(), 1)

    # ── never guess: ambiguous → separate + review ──────────────────────────
    def test_ambiguous_first_name_routes_to_review_not_a_wrong_merge(self):
        PersonA.objects.create(owner=self.user, first_name="Heather", last_name="Jenkins")
        PersonA.objects.create(owner=self.user, first_name="Heather", last_name="Smith")
        c = PersonC.objects.create(user=self.user, display_name="Heather")  # which one? unknown
        result = self._run()
        self.assertEqual(result["ai_relationships"]["review"], 1)
        # A distinct canonical person was created and flagged — NOT merged into either.
        self.assertEqual(Person.objects.filter(user=self.user).count(), 3)
        review_person = PersonSourceLink.objects.get(
            source_domain="ai_relationships", source_pk=c.pk).person
        self.assertTrue(PersonEvent.objects.filter(
            person=review_person, event_type=PersonEvent.Type.DUPLICATE_DETECTED).exists())

    def test_same_name_different_users_never_cross(self):
        PersonA.objects.create(owner=self.user, first_name="John", last_name="Smith")
        PersonA.objects.create(owner=self.other, first_name="John", last_name="Smith")
        self._run()
        self.assertEqual(Person.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Person.objects.filter(user=self.other).count(), 1)

    # ── idempotent ──────────────────────────────────────────────────────────
    def test_rerun_produces_no_duplicates(self):
        PersonA.objects.create(owner=self.user, first_name="Heather", last_name="Jenkins")
        PersonC.objects.create(user=self.user, display_name="Heather")
        self._run()
        first_count = Person.objects.count()
        first_links = PersonSourceLink.objects.count()
        result2 = self._run()
        self.assertEqual(Person.objects.count(), first_count)
        self.assertEqual(PersonSourceLink.objects.count(), first_links)
        self.assertEqual(result2["relationships"]["already_linked"], 1)
        self.assertEqual(result2["ai_relationships"]["already_linked"], 1)

    # ── soft-deleted / inactive are skipped ─────────────────────────────────
    def test_soft_deleted_and_inactive_are_not_migrated(self):
        PersonA.objects.create(owner=self.user, first_name="Gone", last_name="Contact",
                               status="deleted")
        PersonC.objects.create(user=self.user, display_name="Inactive Extraction", is_active=False)
        self._run()
        self.assertEqual(Person.objects.filter(user=self.user).count(), 0)

    def test_membership_grant_source_differs_by_store(self):
        PersonA.objects.create(owner=self.user, first_name="Contact", last_name="Person")
        PersonC.objects.create(user=self.user, display_name="Extracted Person")
        self._run()
        contact = Person.objects.get(user=self.user, first_name="Contact")
        extracted = Person.objects.get(user=self.user, first_name="Extracted")
        self.assertEqual(contact.membership.granted_via, PersonMembership.Grant.CONTACT_IMPORT)
        self.assertEqual(extracted.membership.granted_via, PersonMembership.Grant.MENTION)
