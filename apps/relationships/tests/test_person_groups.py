"""
Whole Life Journey - Person Group Tests

Project: Whole Life Journey
Path: apps/relationships/tests/test_person_groups.py
Purpose: Tests for PersonGroup model, CRUD views, and quick-create API

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json

from django.test import TestCase
from django.urls import reverse

from apps.relationships.models import Person, PersonGroup
from apps.relationships.tests.test_relationships_core import RelationshipsTestMixin


# =============================================================================
# MODEL TESTS
# =============================================================================


class PersonGroupModelTest(RelationshipsTestMixin, TestCase):
    """Tests for the PersonGroup model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_group(self):
        group = PersonGroup.objects.create(owner=self.user, name='Family')
        self.assertEqual(group.name, 'Family')
        self.assertEqual(group.owner, self.user)
        self.assertEqual(group.member_count, 0)

    def test_add_members(self):
        group = PersonGroup.objects.create(owner=self.user, name='Friends')
        p1 = self.create_person(self.user, first_name='Alice')
        p2 = self.create_person(self.user, first_name='Bob')
        group.members.add(p1, p2)
        self.assertEqual(group.member_count, 2)
        self.assertIn(p1, group.members.all())

    def test_soft_delete(self):
        group = PersonGroup.objects.create(owner=self.user, name='Test')
        group.soft_delete()
        self.assertEqual(PersonGroup.objects.filter(owner=self.user).count(), 0)
        self.assertEqual(PersonGroup.all_objects.filter(owner=self.user).count(), 1)

    def test_unique_name_per_owner(self):
        PersonGroup.objects.create(owner=self.user, name='Team')
        with self.assertRaises(Exception):
            PersonGroup.objects.create(owner=self.user, name='Team')

    def test_different_owners_same_name(self):
        other_user = self.create_user(email='other@example.com')
        PersonGroup.objects.create(owner=self.user, name='Shared Name')
        group2 = PersonGroup.objects.create(owner=other_user, name='Shared Name')
        self.assertIsNotNone(group2.pk)

    def test_str(self):
        group = PersonGroup.objects.create(owner=self.user, name='Church Group')
        self.assertEqual(str(group), 'Church Group')

    def test_person_groups_reverse(self):
        """Person.groups reverse relation works."""
        group = PersonGroup.objects.create(owner=self.user, name='Test')
        p = self.create_person(self.user)
        group.members.add(p)
        self.assertIn(group, p.groups.all())


# =============================================================================
# VIEW TESTS
# =============================================================================


class GroupListViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_list_empty(self):
        response = self.client.get(reverse('relationships:group_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No groups yet')

    def test_list_with_groups(self):
        PersonGroup.objects.create(owner=self.user, name='Family')
        PersonGroup.objects.create(owner=self.user, name='Friends')
        response = self.client.get(reverse('relationships:group_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Family')
        self.assertContains(response, 'Friends')
        self.assertContains(response, '2 groups')

    def test_list_scoped_to_owner(self):
        other = self.create_user(email='other@example.com')
        PersonGroup.objects.create(owner=other, name='Private')
        response = self.client.get(reverse('relationships:group_list'))
        self.assertNotContains(response, 'Private')

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('relationships:group_list'))
        self.assertEqual(response.status_code, 302)


class GroupCreateViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_create_page_renders(self):
        response = self.client.get(reverse('relationships:group_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Group')

    def test_create_group(self):
        p = self.create_person(self.user)
        response = self.client.post(reverse('relationships:group_create'), {
            'name': 'Small Group',
            'description': 'Weekly meetup',
            'members': [p.pk],
        })
        self.assertEqual(response.status_code, 302)
        group = PersonGroup.objects.get(owner=self.user, name='Small Group')
        self.assertEqual(group.description, 'Weekly meetup')
        self.assertEqual(group.member_count, 1)

    def test_create_group_no_members(self):
        response = self.client.post(reverse('relationships:group_create'), {
            'name': 'Empty Group',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PersonGroup.objects.filter(name='Empty Group').exists())

    def test_create_duplicate_name_rejected(self):
        PersonGroup.objects.create(owner=self.user, name='Existing')
        response = self.client.post(reverse('relationships:group_create'), {
            'name': 'Existing',
        })
        # Should not create — form error
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PersonGroup.objects.filter(name='Existing').count(), 1)


class GroupDetailViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.group = PersonGroup.objects.create(owner=self.user, name='Test Group')

    def test_detail_renders(self):
        response = self.client.get(reverse('relationships:group_detail', kwargs={'pk': self.group.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Group')

    def test_detail_shows_members(self):
        p = self.create_person(self.user, first_name='Alice')
        self.group.members.add(p)
        response = self.client.get(reverse('relationships:group_detail', kwargs={'pk': self.group.pk}))
        self.assertContains(response, 'Alice')

    def test_detail_scoped_to_owner(self):
        other = self.create_user(email='other@example.com')
        other_group = PersonGroup.objects.create(owner=other, name='Private')
        response = self.client.get(reverse('relationships:group_detail', kwargs={'pk': other_group.pk}))
        self.assertEqual(response.status_code, 404)


class GroupUpdateViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.group = PersonGroup.objects.create(owner=self.user, name='Original')

    def test_update_page_renders(self):
        response = self.client.get(reverse('relationships:group_update', kwargs={'pk': self.group.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Original')

    def test_update_group(self):
        response = self.client.post(
            reverse('relationships:group_update', kwargs={'pk': self.group.pk}),
            {'name': 'Updated', 'description': 'New desc'},
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'Updated')
        self.assertEqual(self.group.description, 'New desc')


class GroupDeleteViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.group = PersonGroup.objects.create(owner=self.user, name='ToDelete')

    def test_delete_soft_deletes(self):
        response = self.client.post(reverse('relationships:group_delete', kwargs={'pk': self.group.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PersonGroup.objects.filter(owner=self.user).count(), 0)

    def test_delete_scoped_to_owner(self):
        other = self.create_user(email='other@example.com')
        other_group = PersonGroup.objects.create(owner=other, name='Private')
        response = self.client.post(reverse('relationships:group_delete', kwargs={'pk': other_group.pk}))
        self.assertEqual(response.status_code, 404)


# =============================================================================
# QUICK CREATE API TESTS
# =============================================================================


class GroupQuickCreateViewTest(RelationshipsTestMixin, TestCase):

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_quick_create_success(self):
        p1 = self.create_person(self.user, first_name='Alice')
        p2 = self.create_person(self.user, first_name='Bob')
        response = self.client.post(
            reverse('relationships:group_quick_create'),
            data=json.dumps({
                'name': 'Quick Group',
                'person_ids': [p1.pk, p2.pk],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['name'], 'Quick Group')
        self.assertEqual(data['member_count'], 2)

    def test_quick_create_no_name(self):
        response = self.client.post(
            reverse('relationships:group_quick_create'),
            data=json.dumps({'name': '', 'person_ids': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_quick_create_duplicate_name(self):
        PersonGroup.objects.create(owner=self.user, name='Existing')
        response = self.client.post(
            reverse('relationships:group_quick_create'),
            data=json.dumps({'name': 'Existing', 'person_ids': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('already exists', response.json()['error'])

    def test_quick_create_ignores_other_users_people(self):
        other = self.create_user(email='other@example.com')
        other_person = self.create_person(other, first_name='Secret')
        response = self.client.post(
            reverse('relationships:group_quick_create'),
            data=json.dumps({
                'name': 'Test',
                'person_ids': [other_person.pk],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        # Should not include other user's person
        self.assertEqual(response.json()['member_count'], 0)

    def test_quick_create_requires_login(self):
        self.client.logout()
        response = self.client.post(
            reverse('relationships:group_quick_create'),
            data=json.dumps({'name': 'Test', 'person_ids': []}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)
