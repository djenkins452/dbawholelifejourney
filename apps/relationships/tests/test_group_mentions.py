"""
Whole Life Journey - Group Mention Tests (Phase 4)

Project: Whole Life Journey
Path: apps/relationships/tests/test_group_mentions.py
Purpose: Tests for @groupname mention expansion and group autocomplete

Coverage:
    - @groupname expands to all group members
    - Case-insensitive group matching
    - Group members get individual Mention + Interaction records
    - No duplicate mentions when member also @mentioned individually
    - Autocomplete returns groups alongside people
    - Groups appear before people in autocomplete results
    - Group results show member count
    - No cross-user group leakage

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.relationships.models import Mention, Person, PersonGroup, RelationshipInteraction
from apps.relationships.services import MentionParserService

User = get_user_model()


# =============================================================================
# HELPERS
# =============================================================================


class GroupMentionTestMixin:
    """Common setup for group mention tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_person(self, owner, first_name='John', last_name='Smith',
                      relationship_type='friend'):
        return Person.objects.create(
            owner=owner,
            first_name=first_name,
            last_name=last_name,
            relationship_type=relationship_type,
        )

    def create_group(self, owner, name, members=None):
        group = PersonGroup.objects.create(owner=owner, name=name)
        if members:
            group.members.set(members)
        return group

    def _make_source_obj(self, user=None):
        """Create a source object for mention linking."""
        from apps.journal.models import JournalEntry
        return JournalEntry.objects.create(
            user=user or self.user,
            title='Test',
            body='Test body',
            entry_date=date.today(),
        )


# =============================================================================
# 1. GROUP MENTION EXPANSION TESTS
# =============================================================================


class GroupMentionParserTest(GroupMentionTestMixin, TestCase):
    """Tests for @groupname → expand to all members."""

    def setUp(self):
        self.user = self.create_user()
        self.alice = self.create_person(self.user, 'Alice', 'Anderson')
        self.bob = self.create_person(self.user, 'Bob', 'Baker')
        self.carol = self.create_person(self.user, 'Carol', 'Chen')
        self.group = self.create_group(
            self.user, 'Small Group',
            members=[self.alice, self.bob, self.carol],
        )

    def test_group_mention_expands_to_all_members(self):
        """@groupname should create mentions for every member."""
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Prayed with @"Small Group" tonight', entry,
        )
        self.assertEqual(len(mentions), 3)
        mentioned_ids = {m.person_id for m in mentions}
        self.assertIn(self.alice.pk, mentioned_ids)
        self.assertIn(self.bob.pk, mentioned_ids)
        self.assertIn(self.carol.pk, mentioned_ids)

    def test_group_mention_creates_interactions(self):
        """Each group member should get an interaction record."""
        entry = self._make_source_obj()
        MentionParserService.parse_and_link(
            self.user, 'Met with @"Small Group" today', entry,
        )
        for person in [self.alice, self.bob, self.carol]:
            self.assertTrue(
                RelationshipInteraction.objects.filter(
                    person=person, user=self.user,
                ).exists(),
                f"Interaction not created for {person.first_name}",
            )

    def test_group_mention_case_insensitive(self):
        """@groupname matching should be case-insensitive."""
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Talked to @"small group" about plans', entry,
        )
        self.assertEqual(len(mentions), 3)

    def test_no_duplicate_when_member_also_mentioned(self):
        """If @Alice and @SmallGroup both appear, Alice gets only one mention."""
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, '@Alice Anderson and @"Small Group" had dinner', entry,
        )
        # Alice appears in group AND individually, but should only have 1 mention
        alice_mentions = [m for m in mentions if m.person_id == self.alice.pk]
        self.assertEqual(len(alice_mentions), 1)
        # Total should be 3 (all group members), not 4
        self.assertEqual(len(mentions), 3)

    def test_group_mention_single_word_name(self):
        """Groups with single-word names should match without quotes."""
        family = self.create_group(
            self.user, 'Family', members=[self.alice, self.bob],
        )
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Dinner with @Family tonight', entry,
        )
        self.assertEqual(len(mentions), 2)
        mentioned_ids = {m.person_id for m in mentions}
        self.assertIn(self.alice.pk, mentioned_ids)
        self.assertIn(self.bob.pk, mentioned_ids)

    def test_empty_group_creates_no_mentions(self):
        """An empty group should not create any mentions."""
        empty_group = self.create_group(self.user, 'Empty', members=[])
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Meeting with @Empty today', entry,
        )
        # No group members, but "Empty" could match a bare name — no persons though
        group_mentions = Mention.objects.filter(object_id=entry.pk)
        self.assertEqual(group_mentions.count(), 0)

    def test_no_cross_user_group_expansion(self):
        """Groups from another user should not expand."""
        user2 = self.create_user(email='user2@example.com')
        other_person = self.create_person(user2, 'Dave', 'Davis')
        self.create_group(user2, 'Small Group', members=[other_person])

        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, '@"Small Group" dinner', entry,
        )
        # Should match OUR Small Group (3 members), not user2's
        self.assertEqual(len(mentions), 3)
        mentioned_ids = {m.person_id for m in mentions}
        self.assertNotIn(other_person.pk, mentioned_ids)

    def test_group_with_bare_name_match(self):
        """Group name in bare text (no @) should NOT expand — only @mentions."""
        entry = self._make_source_obj()
        mentions = MentionParserService.parse_and_link(
            self.user, 'Talked to the Small Group about events', entry,
        )
        # "Small Group" as bare text should NOT trigger group expansion
        # (only @-prefixed mentions trigger group expansion)
        # Individual bare name matching may pick up Alice/Bob/Carol if in text
        group_expanded = len(mentions)
        self.assertNotEqual(group_expanded, 3)  # Should not be all 3 from group


# =============================================================================
# 2. _find_group METHOD TESTS
# =============================================================================


class FindGroupTest(GroupMentionTestMixin, TestCase):
    """Tests for MentionParserService._find_group."""

    def setUp(self):
        self.user = self.create_user()
        self.alice = self.create_person(self.user, 'Alice', 'Anderson')
        self.group = self.create_group(
            self.user, 'Bible Study', members=[self.alice],
        )
        self.groups_qs = PersonGroup.objects.filter(owner=self.user)

    def test_exact_match(self):
        result = MentionParserService._find_group(self.groups_qs, 'Bible Study')
        self.assertEqual(result, self.group)

    def test_case_insensitive_match(self):
        result = MentionParserService._find_group(self.groups_qs, 'bible study')
        self.assertEqual(result, self.group)

    def test_no_match_returns_none(self):
        result = MentionParserService._find_group(self.groups_qs, 'Nonexistent')
        self.assertIsNone(result)

    def test_whitespace_trimmed(self):
        result = MentionParserService._find_group(self.groups_qs, '  Bible Study  ')
        self.assertEqual(result, self.group)


# =============================================================================
# 3. AUTOCOMPLETE WITH GROUPS TESTS
# =============================================================================


class AutocompleteGroupTest(GroupMentionTestMixin, TestCase):
    """Tests for autocomplete returning groups alongside people."""

    def setUp(self):
        self.user = self.create_user()
        self.alice = self.create_person(self.user, 'Alice', 'Anderson')
        self.bob = self.create_person(self.user, 'Bob', 'Baker')
        self.group = self.create_group(
            self.user, 'Alpha Team', members=[self.alice, self.bob],
        )
        self.login_user()

    def test_groups_returned_in_autocomplete(self):
        """Groups matching query should appear in autocomplete results."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Alpha',
        )
        data = json.loads(response.content)
        group_results = [r for r in data if r.get('is_group')]
        self.assertEqual(len(group_results), 1)
        self.assertEqual(group_results[0]['name'], 'Alpha Team')

    def test_groups_appear_before_people(self):
        """Groups should appear before people in results."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Al',
        )
        data = json.loads(response.content)
        # First result should be the group (Alpha Team), then Alice
        self.assertTrue(len(data) >= 2)
        self.assertTrue(data[0]['is_group'])
        self.assertEqual(data[0]['name'], 'Alpha Team')

    def test_group_result_shows_member_count(self):
        """Group type should include member count."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Alpha',
        )
        data = json.loads(response.content)
        group_result = [r for r in data if r.get('is_group')][0]
        self.assertIn('2 members', group_result['type'])

    def test_group_result_has_is_group_flag(self):
        """Group results should have is_group: true."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Alpha',
        )
        data = json.loads(response.content)
        group_result = [r for r in data if r.get('is_group')][0]
        self.assertTrue(group_result['is_group'])

    def test_person_result_has_is_group_false(self):
        """Person results should have is_group: false."""
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Alice',
        )
        data = json.loads(response.content)
        person_results = [r for r in data if not r.get('is_group')]
        self.assertTrue(len(person_results) >= 1)
        self.assertFalse(person_results[0]['is_group'])

    def test_no_cross_user_groups_in_autocomplete(self):
        """Other user's groups should not appear."""
        user2 = self.create_user(email='user2@example.com')
        self.create_group(user2, 'Alpha Secret', members=[])

        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Alpha',
        )
        data = json.loads(response.content)
        group_results = [r for r in data if r.get('is_group')]
        # Only our Alpha Team, not user2's Alpha Secret
        self.assertEqual(len(group_results), 1)
        self.assertEqual(group_results[0]['name'], 'Alpha Team')

    def test_singular_member_count(self):
        """Single member group should say 'member' not 'members'."""
        solo_group = self.create_group(
            self.user, 'Solo Squad', members=[self.alice],
        )
        response = self.client.get(
            reverse('relationships:autocomplete') + '?q=Solo',
        )
        data = json.loads(response.content)
        group_result = [r for r in data if r.get('is_group')][0]
        self.assertIn('1 member', group_result['type'])
        self.assertNotIn('1 members', group_result['type'])
