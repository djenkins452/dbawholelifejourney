"""
Whole Life Journey - Relationships Core Tests

Project: Whole Life Journey
Path: apps/relationships/tests/test_relationships_core.py
Purpose: Comprehensive tests for relational intelligence platform

Coverage:
    - Person creation, display name generation, soft delete
    - Mention parsing (@mention + bare name matching)
    - Interaction recording + deduplication
    - Analytics summary accuracy
    - GenericForeignKey linking
    - Permission enforcement (owner scoping)
    - Autocomplete endpoint
    - Quick-create endpoint

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.relationships.models import Mention, Person, RelationshipInteraction
from apps.relationships.services import MentionParserService, RelationshipAnalyticsService

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================


class RelationshipsTestMixin:
    """Common setup for relationships tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )

    def _complete_onboarding(self, user):
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_person(self, owner, first_name='John', last_name='Smith',
                      relationship_type='friend', **kwargs):
        return Person.objects.create(
            owner=owner,
            first_name=first_name,
            last_name=last_name,
            relationship_type=relationship_type,
            **kwargs,
        )


# =============================================================================
# 1. PERSON MODEL TESTS
# =============================================================================


class PersonModelTest(RelationshipsTestMixin, TestCase):
    """Tests for the Person model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_person_basic(self):
        person = self.create_person(self.user)
        self.assertEqual(person.first_name, 'John')
        self.assertEqual(person.last_name, 'Smith')
        self.assertEqual(person.owner, self.user)
        self.assertEqual(person.relationship_type, 'friend')

    def test_display_name_auto_generated(self):
        person = self.create_person(self.user, first_name='Jane', last_name='Doe')
        self.assertEqual(person.display_name, 'Jane Doe')

    def test_display_name_first_name_only(self):
        person = self.create_person(self.user, first_name='Heather', last_name='')
        self.assertEqual(person.display_name, 'Heather')

    def test_full_name_property(self):
        person = self.create_person(self.user)
        self.assertEqual(person.full_name, 'John Smith')

    def test_soft_delete(self):
        person = self.create_person(self.user)
        person.soft_delete()
        self.assertFalse(Person.objects.filter(pk=person.pk).exists())
        self.assertTrue(Person.all_objects.filter(pk=person.pk).exists())

    def test_restore_after_soft_delete(self):
        person = self.create_person(self.user)
        person.soft_delete()
        person.restore()
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def test_unique_active_person_per_owner(self):
        """Duplicate first+last name for same owner should raise error."""
        self.create_person(self.user, first_name='Alice', last_name='Wonder')
        with self.assertRaises(Exception):
            self.create_person(self.user, first_name='Alice', last_name='Wonder')

    def test_same_name_different_owners(self):
        """Different users can have contacts with the same name."""
        user2 = self.create_user(email='user2@example.com')
        p1 = self.create_person(self.user, first_name='Bob', last_name='Jones')
        p2 = self.create_person(user2, first_name='Bob', last_name='Jones')
        self.assertNotEqual(p1.pk, p2.pk)

    def test_str_representation(self):
        person = self.create_person(self.user)
        self.assertIn('John Smith', str(person))
        self.assertIn('friend', str(person))

    def test_relationship_type_choices(self):
        for type_val, _ in Person.RELATIONSHIP_TYPE_CHOICES:
            person = Person.objects.create(
                owner=self.user,
                first_name=f'Test_{type_val}',
                relationship_type=type_val,
            )
            self.assertEqual(person.relationship_type, type_val)

    def test_optional_fields_nullable(self):
        person = Person.objects.create(
            owner=self.user,
            first_name='Minimal',
        )
        self.assertIsNone(person.email)
        self.assertIsNone(person.phone)
        self.assertIsNone(person.household)
        self.assertIsNone(person.last_interaction_date)
        self.assertEqual(person.interaction_count, 0)

    def test_ordering_by_first_name(self):
        self.create_person(self.user, first_name='Charlie')
        self.create_person(self.user, first_name='Alice')
        self.create_person(self.user, first_name='Bob')
        names = list(
            Person.objects.filter(owner=self.user)
            .values_list('first_name', flat=True)
        )
        self.assertEqual(names, ['Alice', 'Bob', 'Charlie'])


# =============================================================================
# 2. MENTION PARSING TESTS
# =============================================================================


class MentionParserTest(RelationshipsTestMixin, TestCase):
    """Tests for MentionParserService."""

    def setUp(self):
        self.user = self.create_user()
        self.person_john = self.create_person(
            self.user, first_name='John', last_name='Smith',
        )
        self.person_heather = self.create_person(
            self.user, first_name='Heather', last_name='',
        )

    def _make_source_obj(self):
        """Create a mock source object for mention linking."""
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Test body',
            entry_date=date.today(),
        )

    def test_at_mention_pattern(self):
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Had lunch with @John Smith today', entry,
        )
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].person, self.person_john)

    def test_bare_name_detection(self):
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Talked to Heather about the project', entry,
        )
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].person, self.person_heather)

    def test_multiple_mentions(self):
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user,
            'Met with John and Heather for dinner',
            entry,
        )
        self.assertEqual(len(mentions), 2)
        mentioned_ids = {m.person_id for m in mentions}
        self.assertIn(self.person_john.pk, mentioned_ids)
        self.assertIn(self.person_heather.pk, mentioned_ids)

    def test_no_mentions_in_empty_text(self):
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(self.user, '', entry)
        self.assertEqual(len(mentions), 0)

    def test_no_mentions_when_no_contacts(self):
        user2 = self.create_user(email='empty@example.com')
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(user2, '@John Smith', entry)
        self.assertEqual(len(mentions), 0)

    def test_mention_deduplication(self):
        """Same person mentioned twice in same source creates only one Mention."""
        entry = self._make_source_obj()
        MentionParserService.parse_and_link(
            self.user, 'John did this. John also did that.', entry,
        )
        mention_count = Mention.objects.filter(
            person=self.person_john,
            object_id=entry.pk,
        ).count()
        self.assertEqual(mention_count, 1)

    def test_case_insensitive_matching(self):
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Talked to heather today', entry,
        )
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].person, self.person_heather)

    def test_word_boundary_matching(self):
        """Should not match partial names (e.g., 'john' inside 'johnson')."""
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Met with Johnson today', entry,
        )
        # 'John' is a substring of 'Johnson' but word boundary should prevent match
        # Note: 'John' will match in 'Johnson' since \bJohn\b matches inside Johnson
        # Actually \bJohn\b would match "John" but not "Johnson" since the "s" breaks boundary
        # Let's check: \bjohn\b in "johnson" — 'j' is a word char, so \b is before 'j' only
        # if preceded by non-word char. "met with johnson" → \bjohnson\b matches, \bjohn\b does NOT.
        john_mentions = [m for m in mentions if m.person == self.person_john]
        self.assertEqual(len(john_mentions), 0)

    def test_context_type_auto_detection(self):
        entry = self._make_source_obj()
        MentionParserService.parse_and_link(
            self.user, 'Lunch with John', entry,
        )
        interaction = RelationshipInteraction.objects.filter(
            person=self.person_john,
        ).first()
        self.assertIsNotNone(interaction)
        self.assertEqual(interaction.context_type_label, 'journal')


# =============================================================================
# 3. INTERACTION RECORDING TESTS
# =============================================================================


class InteractionRecordingTest(RelationshipsTestMixin, TestCase):
    """Tests for RelationshipAnalyticsService.record_interaction."""

    def setUp(self):
        self.user = self.create_user()
        self.person = self.create_person(self.user)

    def test_record_interaction_basic(self):
        interaction = RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        self.assertIsNotNone(interaction)
        self.assertEqual(interaction.person, self.person)
        self.assertEqual(interaction.context_type_label, 'journal')

    def test_updates_denormalized_counters(self):
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        self.person.refresh_from_db()
        self.assertEqual(self.person.interaction_count, 1)
        self.assertEqual(self.person.last_interaction_date, timezone.localdate())

    def test_deduplication_with_source_object(self):
        """Same person + source object should not create duplicate."""
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user, title='Test', body='Body', entry_date=date.today(),
        )
        i1 = RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal', source_obj=entry,
        )
        i2 = RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal', source_obj=entry,
        )
        self.assertIsNotNone(i1)
        self.assertIsNone(i2)  # Deduplicated

    def test_multiple_context_types(self):
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'task',
        )
        self.person.refresh_from_db()
        self.assertEqual(self.person.interaction_count, 2)


# =============================================================================
# 4. ANALYTICS SUMMARY TESTS
# =============================================================================


class AnalyticsSummaryTest(RelationshipsTestMixin, TestCase):
    """Tests for RelationshipAnalyticsService summary methods."""

    def setUp(self):
        self.user = self.create_user()
        self.person = self.create_person(self.user)

    def test_get_summary_empty(self):
        summary = RelationshipAnalyticsService.get_summary(self.person)
        self.assertEqual(summary['total_interactions'], 0)
        self.assertIsNone(summary['last_interaction_date'])
        self.assertEqual(summary['journal_mentions'], 0)

    def test_get_summary_with_data(self):
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'prayer',
        )
        summary = RelationshipAnalyticsService.get_summary(self.person)
        self.assertEqual(summary['total_interactions'], 2)
        self.assertEqual(summary['journal_mentions'], 1)
        self.assertEqual(summary['prayer_mentions'], 1)
        self.assertIsNotNone(summary['last_interaction_date'])

    def test_context_breakdown(self):
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'task',
        )
        breakdown = RelationshipAnalyticsService.context_breakdown(self.person)
        self.assertEqual(breakdown.get('journal'), 2)
        self.assertEqual(breakdown.get('task'), 1)

    def test_days_since_last_interaction(self):
        self.assertIsNone(
            RelationshipAnalyticsService.days_since_last_interaction(self.person)
        )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        days = RelationshipAnalyticsService.days_since_last_interaction(self.person)
        self.assertEqual(days, 0)

    def test_interaction_count_with_timeframe(self):
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'journal',
        )
        count = RelationshipAnalyticsService.interaction_count(
            self.person, timeframe=timedelta(days=7),
        )
        self.assertEqual(count, 1)

    def test_top_interacted(self):
        person2 = self.create_person(
            self.user, first_name='Jane', last_name='Doe',
        )
        # Give person2 more interactions
        for _ in range(3):
            RelationshipAnalyticsService.record_interaction(
                person2, self.user, 'journal',
            )
        RelationshipAnalyticsService.record_interaction(
            self.person, self.user, 'task',
        )
        top = list(RelationshipAnalyticsService.top_interacted(self.user, limit=10))
        self.assertEqual(top[0], person2)  # More interactions first


# =============================================================================
# 5. GENERIC FOREIGN KEY TESTS
# =============================================================================


class GenericForeignKeyTest(RelationshipsTestMixin, TestCase):
    """Tests for GenericForeignKey linking on Mention and Interaction."""

    def setUp(self):
        self.user = self.create_user()
        self.person = self.create_person(self.user)

    def test_mention_generic_fk(self):
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user, title='GFK Test', body='Body',
            entry_date=date.today(),
        )
        ct = ContentType.objects.get_for_model(entry)
        mention = Mention.objects.create(
            person=self.person,
            content_type=ct,
            object_id=entry.pk,
        )
        self.assertEqual(mention.content_object, entry)

    def test_interaction_generic_fk(self):
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user, title='GFK Test', body='Body',
            entry_date=date.today(),
        )
        ct = ContentType.objects.get_for_model(entry)
        interaction = RelationshipInteraction.objects.create(
            person=self.person,
            user=self.user,
            context_type_label='journal',
            interaction_date=date.today(),
            content_type=ct,
            object_id=entry.pk,
        )
        self.assertEqual(interaction.source_object, entry)

    def test_unique_mention_per_object_constraint(self):
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user, title='Constraint Test', body='Body',
            entry_date=date.today(),
        )
        ct = ContentType.objects.get_for_model(entry)
        Mention.objects.create(
            person=self.person, content_type=ct, object_id=entry.pk,
        )
        with self.assertRaises(Exception):
            Mention.objects.create(
                person=self.person, content_type=ct, object_id=entry.pk,
            )


# =============================================================================
# 6. PERMISSION ENFORCEMENT TESTS
# =============================================================================


class PermissionEnforcementTest(RelationshipsTestMixin, TestCase):
    """Tests that contacts are scoped to their owner."""

    def setUp(self):
        self.user1 = self.create_user(email='user1@example.com')
        self.user2 = self.create_user(email='user2@example.com')
        self.person = self.create_person(self.user1)

    def test_owner_can_see_their_contacts(self):
        contacts = Person.objects.filter(owner=self.user1)
        self.assertEqual(contacts.count(), 1)

    def test_other_user_cannot_see_contacts(self):
        contacts = Person.objects.filter(owner=self.user2)
        self.assertEqual(contacts.count(), 0)

    def test_detail_view_rejects_wrong_owner(self):
        self.login_user(email='user2@example.com')
        response = self.client.get(
            reverse('relationships:person_detail', kwargs={'pk': self.person.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_update_view_rejects_wrong_owner(self):
        self.login_user(email='user2@example.com')
        response = self.client.get(
            reverse('relationships:person_update', kwargs={'pk': self.person.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_rejects_wrong_owner(self):
        self.login_user(email='user2@example.com')
        response = self.client.post(
            reverse('relationships:person_delete', kwargs={'pk': self.person.pk}),
        )
        self.assertEqual(response.status_code, 404)


# =============================================================================
# 7. AUTOCOMPLETE ENDPOINT TESTS
# =============================================================================


class AutocompleteEndpointTest(RelationshipsTestMixin, TestCase):
    """Tests for /relationships/autocomplete/ API."""

    def setUp(self):
        self.user = self.create_user()
        self.person = self.create_person(self.user, first_name='Sarah', last_name='Connor')
        self.login_user()

    def test_search_by_first_name(self):
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Sar',
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'Sarah Connor')

    def test_search_by_last_name(self):
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Con',
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)

    def test_empty_query_returns_recent_contacts(self):
        """Empty query returns recent contacts (for bare @ trigger)."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=',
        )
        data = json.loads(response.content)
        # Should return the user's contacts ordered by updated_at
        self.assertGreater(len(data), 0)
        self.assertFalse(data[0]['is_group'])

    def test_no_cross_user_results(self):
        user2 = self.create_user(email='user2@example.com')
        self.create_person(user2, first_name='Private', last_name='Person')
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Private',
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 0)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Sarah',
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login


# =============================================================================
# 8. QUICK CREATE ENDPOINT TESTS
# =============================================================================


class QuickCreateEndpointTest(RelationshipsTestMixin, TestCase):
    """Tests for /relationships/quick-create/ API."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_create_person_via_api(self):
        response = self.client.post(
            reverse('relationships:quick_create'),
            data=json.dumps({
                'first_name': 'Quick',
                'last_name': 'Person',
                'relationship_type': 'coworker',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = json.loads(response.content)
        self.assertEqual(data['name'], 'Quick Person')
        self.assertTrue(Person.objects.filter(owner=self.user, first_name='Quick').exists())

    def test_missing_first_name_returns_400(self):
        response = self.client.post(
            reverse('relationships:quick_create'),
            data=json.dumps({'last_name': 'Only'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            reverse('relationships:quick_create'),
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


# =============================================================================
# 9. VIEW TESTS
# =============================================================================


class PersonViewTest(RelationshipsTestMixin, TestCase):
    """Tests for Person CRUD views."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_list_view(self):
        self.create_person(self.user)
        response = self.client.get(reverse('relationships:person_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John Smith')

    def test_create_view_get(self):
        response = self.client.get(reverse('relationships:person_create'))
        self.assertEqual(response.status_code, 200)

    def test_create_view_post(self):
        response = self.client.post(reverse('relationships:person_create'), {
            'first_name': 'New',
            'last_name': 'Contact',
            'relationship_type': 'friend',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Person.objects.filter(first_name='New').exists())

    def test_detail_view(self):
        person = self.create_person(self.user)
        response = self.client.get(
            reverse('relationships:person_detail', kwargs={'pk': person.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'John Smith')

    def test_update_view(self):
        person = self.create_person(self.user)
        response = self.client.post(
            reverse('relationships:person_update', kwargs={'pk': person.pk}),
            {
                'first_name': 'Updated',
                'last_name': 'Name',
                'relationship_type': 'family',
            },
        )
        self.assertEqual(response.status_code, 302)
        person.refresh_from_db()
        self.assertEqual(person.first_name, 'Updated')

    def test_delete_view(self):
        person = self.create_person(self.user)
        response = self.client.post(
            reverse('relationships:person_delete', kwargs={'pk': person.pk}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Person.objects.filter(pk=person.pk).exists())

    def test_list_view_search_filter(self):
        self.create_person(self.user, first_name='Alice', last_name='B')
        self.create_person(self.user, first_name='Bob', last_name='C')
        response = self.client.get(
            reverse('relationships:person_list') + '?q=Alice',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')
        self.assertNotContains(response, 'Bob')

    def test_list_view_type_filter(self):
        self.create_person(self.user, first_name='Zaragoza', relationship_type='family')
        self.create_person(self.user, first_name='Xylopho', relationship_type='friend')
        response = self.client.get(
            reverse('relationships:person_list') + '?type=family',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Zaragoza')
        self.assertNotContains(response, 'Xylopho')
