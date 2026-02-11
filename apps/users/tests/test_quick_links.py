"""
Tests for the Quick Links (ExternalLink) feature.

Tests cover:
- Model creation and constraints
- API endpoints (create, delete)
- Max link limit
- URL validation
- Context processor
"""

import json

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.urls import reverse

from apps.users.models import ExternalLink, User


def _complete_user_setup(user):
    """Mark a user as having completed onboarding and accepted terms."""
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    try:
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.get_or_create(
            user=user,
            defaults={'terms_version': settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')},
        )
    except Exception:
        pass


class ExternalLinkModelTest(TestCase):
    """Tests for the ExternalLink model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )

    def test_create_link(self):
        """Should create an external link."""
        link = ExternalLink.objects.create(
            user=self.user,
            name='Patient Portal',
            url='https://myportal.example.com',
        )
        self.assertEqual(link.name, 'Patient Portal')
        self.assertEqual(link.url, 'https://myportal.example.com')
        self.assertEqual(link.sort_order, 0)

    def test_str_representation(self):
        """Should show name and URL in str."""
        link = ExternalLink.objects.create(
            user=self.user,
            name='Bank',
            url='https://bank.example.com',
        )
        self.assertIn('Bank', str(link))
        self.assertIn('bank.example.com', str(link))

    def test_ordering(self):
        """Should order by sort_order then created_at."""
        link2 = ExternalLink.objects.create(
            user=self.user, name='Second', url='https://b.com', sort_order=2,
        )
        link1 = ExternalLink.objects.create(
            user=self.user, name='First', url='https://a.com', sort_order=1,
        )
        links = list(ExternalLink.get_links_for_user(self.user))
        self.assertEqual(links[0].name, 'First')
        self.assertEqual(links[1].name, 'Second')

    def test_can_add_link(self):
        """Should return True when under the max."""
        self.assertTrue(ExternalLink.can_add_link(self.user))

    def test_max_link_limit(self):
        """Should return False when at the max."""
        for i in range(ExternalLink.MAX_LINKS):
            ExternalLink.objects.create(
                user=self.user,
                name=f'Link {i}',
                url=f'https://example{i}.com',
            )
        self.assertFalse(ExternalLink.can_add_link(self.user))

    def test_links_per_user_isolation(self):
        """Links from one user should not appear for another."""
        other_user = User.objects.create_user(
            email='other@example.com', password='testpass123',
        )
        ExternalLink.objects.create(
            user=self.user, name='Mine', url='https://mine.com',
        )
        ExternalLink.objects.create(
            user=other_user, name='Theirs', url='https://theirs.com',
        )
        my_links = ExternalLink.get_links_for_user(self.user)
        self.assertEqual(my_links.count(), 1)
        self.assertEqual(my_links.first().name, 'Mine')


class QuickLinkCreateAPITest(TestCase):
    """Tests for the quick link create API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        _complete_user_setup(self.user)
        self.client.login(email='test@example.com', password='testpass123')
        self.url = reverse('users:quick_link_create')

    def test_create_link(self):
        """Should create a link and return success."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Portal', 'url': 'https://portal.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['link']['name'], 'Portal')
        self.assertEqual(ExternalLink.objects.filter(user=self.user).count(), 1)

    def test_create_link_missing_name(self):
        """Should reject when name is empty."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': '', 'url': 'https://example.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_create_link_missing_url(self):
        """Should reject when URL is empty."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Test', 'url': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_create_link_invalid_url(self):
        """Should reject invalid URLs."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Test', 'url': 'not-a-url'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('valid URL', response.json()['error'])

    def test_create_link_max_limit(self):
        """Should reject when at max link limit."""
        for i in range(ExternalLink.MAX_LINKS):
            ExternalLink.objects.create(
                user=self.user, name=f'Link {i}', url=f'https://e{i}.com',
            )
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Over Limit', 'url': 'https://over.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Maximum', response.json()['error'])

    def test_create_link_requires_auth(self):
        """Should return redirect for unauthenticated users."""
        self.client.logout()
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Test', 'url': 'https://test.com'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)


class QuickLinkDeleteAPITest(TestCase):
    """Tests for the quick link delete API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        _complete_user_setup(self.user)
        self.client.login(email='test@example.com', password='testpass123')
        self.link = ExternalLink.objects.create(
            user=self.user, name='To Delete', url='https://delete.com',
        )

    def test_delete_link(self):
        """Should delete the link and return success."""
        url = reverse('users:quick_link_delete', args=[self.link.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.assertEqual(ExternalLink.objects.filter(user=self.user).count(), 0)

    def test_delete_nonexistent_link(self):
        """Should return 404 for nonexistent link."""
        url = reverse('users:quick_link_delete', args=[99999])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_delete_other_users_link(self):
        """Should not allow deleting another user's link."""
        other_user = User.objects.create_user(
            email='other@example.com', password='testpass123',
        )
        _complete_user_setup(other_user)
        other_link = ExternalLink.objects.create(
            user=other_user, name='Not Mine', url='https://notmine.com',
        )
        url = reverse('users:quick_link_delete', args=[other_link.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        # Link should still exist
        self.assertTrue(ExternalLink.objects.filter(id=other_link.id).exists())


class QuickLinksContextProcessorTest(TestCase):
    """Tests for the quick_links_context processor."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        _complete_user_setup(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def test_links_in_context(self):
        """Quick links should be available in template context."""
        ExternalLink.objects.create(
            user=self.user, name='Portal', url='https://portal.com',
        )
        # Clear cache so the context processor fetches fresh data
        from django.core.cache import cache
        cache.delete(f'quick_links_user_{self.user.id}')

        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        quick_links = response.context.get('quick_links_list', [])
        self.assertEqual(len(quick_links), 1)
        self.assertEqual(quick_links[0]['name'], 'Portal')

    def test_empty_links_for_new_user(self):
        """Should return empty list when user has no links."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
        quick_links = response.context.get('quick_links_list', [])
        self.assertEqual(len(quick_links), 0)
