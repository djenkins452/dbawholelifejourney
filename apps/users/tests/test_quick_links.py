"""
Tests for the Quick Links (ExternalLink) feature.

Tests cover:
- Model creation, constraints, and new fields
- API endpoints (create, delete, update, open/redirect)
- Max link limit
- URL validation
- Mobile deep link detection and redirect
- Usage counter
- Context processor
- Intelligence hook (get_most_used_links)
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

    # ---- New field tests ----

    def test_default_field_values(self):
        """New fields should have sensible defaults."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://test.com',
        )
        self.assertEqual(link.mobile_app_url, '')
        self.assertEqual(link.icon, ExternalLink.ICON_LINK)
        self.assertEqual(link.category, ExternalLink.CATEGORY_GENERAL)
        self.assertTrue(link.open_in_new_tab)
        self.assertEqual(link.usage_count, 0)

    def test_has_deep_link_property(self):
        """has_deep_link should reflect mobile_app_url presence."""
        link_no_deep = ExternalLink.objects.create(
            user=self.user, name='No deep', url='https://test.com',
        )
        link_deep = ExternalLink.objects.create(
            user=self.user, name='With deep', url='https://chase.com',
            mobile_app_url='chase://',
        )
        self.assertFalse(link_no_deep.has_deep_link)
        self.assertTrue(link_deep.has_deep_link)

    def test_increment_usage(self):
        """increment_usage should atomically increase usage_count."""
        link = ExternalLink.objects.create(
            user=self.user, name='Counted', url='https://counted.com',
        )
        self.assertEqual(link.usage_count, 0)
        link.increment_usage()
        link.refresh_from_db()
        self.assertEqual(link.usage_count, 1)
        link.increment_usage()
        link.increment_usage()
        link.refresh_from_db()
        self.assertEqual(link.usage_count, 3)

    def test_get_most_used_links(self):
        """get_most_used_links should return links ordered by usage_count."""
        link_a = ExternalLink.objects.create(
            user=self.user, name='Low', url='https://low.com', usage_count=2,
        )
        link_b = ExternalLink.objects.create(
            user=self.user, name='High', url='https://high.com', usage_count=10,
        )
        link_c = ExternalLink.objects.create(
            user=self.user, name='Zero', url='https://zero.com', usage_count=0,
        )
        most_used = list(ExternalLink.get_most_used_links(self.user))
        self.assertEqual(len(most_used), 2)  # Zero-usage excluded
        self.assertEqual(most_used[0].name, 'High')
        self.assertEqual(most_used[1].name, 'Low')

    def test_create_link_with_deep_link(self):
        """Should create a link with mobile_app_url."""
        link = ExternalLink.objects.create(
            user=self.user,
            name='Chase Bank',
            url='https://chase.com',
            mobile_app_url='chase://',
            category=ExternalLink.CATEGORY_FINANCE,
        )
        self.assertEqual(link.mobile_app_url, 'chase://')
        self.assertEqual(link.category, 'finance')


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

    def test_create_link_with_mobile_url(self):
        """Should create a link with mobile_app_url and category."""
        response = self.client.post(
            self.url,
            data=json.dumps({
                'name': 'Chase',
                'url': 'https://chase.com',
                'mobile_app_url': 'chase://',
                'category': 'finance',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['link']['mobile_app_url'], 'chase://')
        self.assertEqual(data['link']['category'], 'finance')

        link = ExternalLink.objects.get(user=self.user)
        self.assertEqual(link.mobile_app_url, 'chase://')
        self.assertEqual(link.category, 'finance')

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

    def test_create_link_invalid_category_falls_back(self):
        """Invalid category should fallback to general."""
        response = self.client.post(
            self.url,
            data=json.dumps({
                'name': 'Test',
                'url': 'https://test.com',
                'category': 'nonexistent',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['link']['category'], 'general')


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
        self.assertTrue(ExternalLink.objects.filter(id=other_link.id).exists())


class QuickLinkUpdateAPITest(TestCase):
    """Tests for the quick link update API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        _complete_user_setup(self.user)
        self.client.login(email='test@example.com', password='testpass123')
        self.link = ExternalLink.objects.create(
            user=self.user, name='Original', url='https://original.com',
        )
        self.url = reverse('users:quick_link_update', args=[self.link.id])

    def test_update_name(self):
        """Should update link name."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': 'Updated Name'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.name, 'Updated Name')

    def test_update_mobile_url(self):
        """Should update mobile_app_url."""
        response = self.client.post(
            self.url,
            data=json.dumps({'mobile_app_url': 'chase://'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.mobile_app_url, 'chase://')

    def test_update_category(self):
        """Should update category."""
        response = self.client.post(
            self.url,
            data=json.dumps({'category': 'finance'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.category, 'finance')

    def test_update_invalid_category_ignored(self):
        """Invalid category should be silently ignored."""
        response = self.client.post(
            self.url,
            data=json.dumps({'category': 'fake_category'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.category, 'general')  # unchanged

    def test_update_other_users_link(self):
        """Should not allow updating another user's link."""
        other_user = User.objects.create_user(
            email='other@example.com', password='testpass123',
        )
        _complete_user_setup(other_user)
        other_link = ExternalLink.objects.create(
            user=other_user, name='Theirs', url='https://theirs.com',
        )
        url = reverse('users:quick_link_update', args=[other_link.id])
        response = self.client.post(
            url,
            data=json.dumps({'name': 'Hacked'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        other_link.refresh_from_db()
        self.assertEqual(other_link.name, 'Theirs')

    def test_update_empty_name_rejected(self):
        """Should reject empty name."""
        response = self.client.post(
            self.url,
            data=json.dumps({'name': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)


class QuickLinkOpenViewTest(TestCase):
    """Tests for the redirect/deep link view."""

    IPHONE_UA = (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
    )
    DESKTOP_UA = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        _complete_user_setup(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def test_desktop_redirects_to_web_url(self):
        """Desktop should get a direct redirect to the web URL."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://chase.com',
            mobile_app_url='chase://',
        )
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url, HTTP_USER_AGENT=self.DESKTOP_UA)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://chase.com')

    def test_mobile_with_deep_link_renders_redirect_page(self):
        """Mobile with deep link should render redirect template."""
        link = ExternalLink.objects.create(
            user=self.user, name='Chase', url='https://chase.com',
            mobile_app_url='chase://',
        )
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url, HTTP_USER_AGENT=self.IPHONE_UA)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/quick_link_redirect.html')
        self.assertContains(response, 'chase://')
        self.assertContains(response, 'https://chase.com')

    def test_mobile_without_deep_link_redirects(self):
        """Mobile without deep link should get a direct redirect."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://example.com',
        )
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url, HTTP_USER_AGENT=self.IPHONE_UA)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://example.com')

    def test_usage_count_incremented(self):
        """Opening a link should increment usage_count."""
        link = ExternalLink.objects.create(
            user=self.user, name='Counted', url='https://counted.com',
        )
        self.assertEqual(link.usage_count, 0)

        url = reverse('users:quick_link_open', args=[link.id])
        self.client.get(url, HTTP_USER_AGENT=self.DESKTOP_UA)
        link.refresh_from_db()
        self.assertEqual(link.usage_count, 1)

        self.client.get(url, HTTP_USER_AGENT=self.DESKTOP_UA)
        link.refresh_from_db()
        self.assertEqual(link.usage_count, 2)

    def test_other_users_link_404(self):
        """Should not allow accessing another user's link."""
        other_user = User.objects.create_user(
            email='other@example.com', password='testpass123',
        )
        other_link = ExternalLink.objects.create(
            user=other_user, name='Secret', url='https://secret.com',
        )
        url = reverse('users:quick_link_open', args=[other_link.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_nonexistent_link_404(self):
        """Should return 404 for nonexistent link."""
        url = reverse('users:quick_link_open', args=[99999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_requires_auth(self):
        """Should redirect unauthenticated users."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://test.com',
        )
        self.client.logout()
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_android_user_agent_detected_as_mobile(self):
        """Android User-Agent should trigger mobile path."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://test.com',
            mobile_app_url='myapp://',
        )
        android_ua = (
            'Mozilla/5.0 (Linux; Android 14; Pixel 8) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        )
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url, HTTP_USER_AGENT=android_ua)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'users/quick_link_redirect.html')

    def test_ipad_user_agent_detected_as_mobile(self):
        """iPad User-Agent should trigger mobile path."""
        link = ExternalLink.objects.create(
            user=self.user, name='Test', url='https://test.com',
            mobile_app_url='myapp://',
        )
        ipad_ua = (
            'Mozilla/5.0 (iPad; CPU OS 17_2 like Mac OS X) '
            'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
        )
        url = reverse('users:quick_link_open', args=[link.id])
        response = self.client.get(url, HTTP_USER_AGENT=ipad_ua)
        self.assertEqual(response.status_code, 200)


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

        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)
        quick_links = response.context.get('quick_links_list', [])
        self.assertEqual(len(quick_links), 1)
        self.assertEqual(quick_links[0]['name'], 'Portal')

    def test_empty_links_for_new_user(self):
        """Should return empty list when user has no links."""
        from django.core.cache import cache
        cache.delete(f'quick_links_user_{self.user.id}')

        response = self.client.get(reverse('dashboard_v2:home'))
        self.assertEqual(response.status_code, 200)
        quick_links = response.context.get('quick_links_list', [])
        self.assertEqual(len(quick_links), 0)

    def test_context_includes_new_fields(self):
        """Context should include mobile_app_url and other new fields."""
        ExternalLink.objects.create(
            user=self.user, name='Chase', url='https://chase.com',
            mobile_app_url='chase://', category='finance',
        )
        from django.core.cache import cache
        cache.delete(f'quick_links_user_{self.user.id}')

        response = self.client.get(reverse('dashboard_v2:home'))
        quick_links = response.context.get('quick_links_list', [])
        self.assertEqual(len(quick_links), 1)
        self.assertEqual(quick_links[0]['mobile_app_url'], 'chase://')
        self.assertEqual(quick_links[0]['category'], 'finance')
        self.assertIn('open_in_new_tab', quick_links[0])
