"""Tests for capture views."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.capture.models import CaptureEntry

User = get_user_model()


class CaptureListViewTests(TestCase):
    """Tests for CaptureListView."""

    def setUp(self):
        """Set up test user and client."""
        self.client = Client()
        self.user = self._create_user()
        self.client.login(email='testuser@example.com', password='testpass123')

    def _create_user(self, email='testuser@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        """Accept terms of service for user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def test_list_view_requires_login(self):
        """List view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_list_view_loads(self):
        """List view loads for authenticated user."""
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.status_code, 200)

    def test_list_view_uses_correct_template(self):
        """List view uses the correct template."""
        response = self.client.get(reverse('capture:list'))
        self.assertTemplateUsed(response, 'capture/capture_list.html')

    def test_list_view_empty_state(self):
        """List view shows empty state when no entries exist."""
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'No recordings yet')

    def test_list_view_shows_user_entries(self):
        """List view shows the user's entries."""
        entry = CaptureEntry.objects.create(
            user=self.user,
            title='My Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'My Recording')

    def test_list_view_does_not_show_other_users_entries(self):
        """List view only shows current user's entries."""
        other_user = self._create_user(
            email='other@example.com',
            password='testpass123'
        )
        CaptureEntry.objects.create(
            user=other_user,
            title='Other User Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertNotContains(response, 'Other User Recording')

    def test_list_view_orders_by_created_at_desc(self):
        """List view orders entries by most recent first."""
        entry1 = CaptureEntry.objects.create(
            user=self.user,
            title='First Recording',
            status=CaptureEntry.STATUS_READY,
        )
        entry2 = CaptureEntry.objects.create(
            user=self.user,
            title='Second Recording',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        entries = list(response.context['entries'])
        self.assertEqual(entries[0].id, entry2.id)
        self.assertEqual(entries[1].id, entry1.id)

    def test_list_view_context_has_counts(self):
        """List view context includes total and ready counts."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY,
        )
        CaptureEntry.objects.create(
            user=self.user,
            title='Processing Entry',
            status=CaptureEntry.STATUS_TRANSCRIBING,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertEqual(response.context['total_count'], 2)
        self.assertEqual(response.context['ready_count'], 1)

    def test_list_view_shows_status(self):
        """List view displays entry status correctly."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Ready Entry',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Ready')

    def test_list_view_shows_failed_status(self):
        """List view displays failed status."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Failed Entry',
            status=CaptureEntry.STATUS_FAILED,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Failed')

    def test_list_view_shows_untitled_for_no_title(self):
        """List view shows 'Untitled Recording' when no title."""
        CaptureEntry.objects.create(
            user=self.user,
            title='',
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Untitled Recording')

    def test_list_view_shows_category(self):
        """List view displays entry category."""
        CaptureEntry.objects.create(
            user=self.user,
            title='Faith Entry',
            category=CaptureEntry.CATEGORY_FAITH,
            subcategory=CaptureEntry.SUBCATEGORY_SERMON,
            status=CaptureEntry.STATUS_READY,
        )
        response = self.client.get(reverse('capture:list'))
        self.assertContains(response, 'Faith')
        self.assertContains(response, 'Sermon')
