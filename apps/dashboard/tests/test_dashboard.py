"""
Dashboard Module Tests

Tests for the main dashboard view and tiles.

Location: apps/dashboard/tests/test_dashboard.py
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


class DashboardViewTest(TestCase):
    """Tests for the main dashboard page."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='John'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
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
    
    def test_dashboard_requires_login(self):
        """Dashboard requires authentication."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_dashboard_loads_for_authenticated_user(self):
        """Authenticated user can access dashboard."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_shows_greeting(self):
        """Dashboard shows personalized greeting."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'John')
    
    def test_dashboard_shows_journal_tile_when_enabled(self):
        """Journal tile appears when journal is enabled."""
        self.user.preferences.journal_enabled = True
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Journal')
    
    def test_dashboard_hides_journal_tile_when_disabled(self):
        """Journal tile is hidden when journal is disabled."""
        self.user.preferences.journal_enabled = False
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        # The tile section shouldn't appear
        self.assertNotContains(response, 'tile-journal')
    
    def test_dashboard_shows_life_tile_when_enabled(self):
        """Life tile appears when life module is enabled."""
        self.user.preferences.life_enabled = True
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Life')
    
    def test_dashboard_shows_faith_tile_when_enabled(self):
        """Faith tile appears when faith module is enabled."""
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Faith')
    
    def test_dashboard_hides_faith_tile_when_disabled(self):
        """Faith tile is hidden when faith module is disabled."""
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertNotContains(response, 'tile-faith')
    
    def test_dashboard_shows_purpose_tile_when_enabled(self):
        """Purpose tile appears when purpose module is enabled."""
        self.user.preferences.purpose_enabled = True
        self.user.preferences.save()
        
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('dashboard:home'))
        self.assertContains(response, 'Purpose')


class DashboardContextTest(TestCase):
    """Tests for dashboard context data."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
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
    
    def test_dashboard_has_greeting_context(self):
        """Dashboard context includes greeting."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertIn('greeting', response.context)
    
    def test_dashboard_has_current_date_context(self):
        """Dashboard context includes current date."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertIn('current_date', response.context)
    
    def test_dashboard_has_module_enabled_flags(self):
        """Dashboard context includes module enabled flags."""
        response = self.client.get(reverse('dashboard:home'))
        self.assertIn('journal_enabled', response.context)
        self.assertIn('life_enabled', response.context)
        self.assertIn('faith_enabled', response.context)