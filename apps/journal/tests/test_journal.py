"""
Journal Module Tests

Tests for journal entries, prompts, and related functionality.

Location: apps/journal/tests/test_journal.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.journal.models import JournalEntry, JournalPrompt

User = get_user_model()


class JournalEntryModelTest(TestCase):
    """Tests for the JournalEntry model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_entry(self):
        """Entry can be created with required fields."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='My First Entry',
            body='Today was a good day.',
            entry_date=date.today()
        )
        self.assertEqual(entry.title, 'My First Entry')
        self.assertEqual(entry.user, self.user)
    
    def test_entry_str(self):
        """Entry string representation includes title."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content here',
            entry_date=date.today()
        )
        self.assertIn('Test Entry', str(entry))
    
    def test_entry_has_created_at(self):
        """Entry automatically gets created_at timestamp."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Timestamped Entry',
            body='Content',
            entry_date=date.today()
        )
        self.assertIsNotNone(entry.created_at)
    
    def test_entry_ordering(self):
        """Entries are ordered by most recent first."""
        entry1 = JournalEntry.objects.create(
            user=self.user,
            title='First Entry',
            body='Content 1',
            entry_date=date.today() - timedelta(days=1)
        )
        entry2 = JournalEntry.objects.create(
            user=self.user,
            title='Second Entry',
            body='Content 2',
            entry_date=date.today()
        )
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries[0], entry2)  # Most recent first


class JournalPromptModelTest(TestCase):
    """Tests for the JournalPrompt model."""
    
    def test_create_prompt(self):
        """Prompt can be created."""
        prompt = JournalPrompt.objects.create(
            text='What are you grateful for today?',
            is_active=True
        )
        self.assertEqual(prompt.text, 'What are you grateful for today?')
        self.assertTrue(prompt.is_active)
    
    def test_prompt_str(self):
        """Prompt string representation is the text."""
        prompt = JournalPrompt.objects.create(
            text='Describe your day',
            is_active=True
        )
        self.assertIn('Describe', str(prompt))


class JournalEntryViewTest(TestCase):
    """Tests for journal entry views."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
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
    
    def test_entry_list_requires_login(self):
        """Entry list requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('journal:entry_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_entry_list_loads(self):
        """Entry list page loads for authenticated user."""
        response = self.client.get(reverse('journal:entry_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_entry_list_shows_user_entries(self):
        """Entry list shows the user's entries."""
        JournalEntry.objects.create(
            user=self.user,
            title='My Entry',
            body='Content',
            entry_date=date.today()
        )
        response = self.client.get(reverse('journal:entry_list'))
        self.assertContains(response, 'My Entry')
    
    def test_entry_create_page_loads(self):
        """Entry creation page loads."""
        response = self.client.get(reverse('journal:entry_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_entry_can_be_created(self):
        """User can create a journal entry."""
        response = self.client.post(reverse('journal:entry_create'), {
            'title': 'New Entry',
            'body': 'This is my journal entry content.',
            'entry_date': date.today().isoformat(),
        })
        
        # Check entry was created (may redirect or show success)
        entry_exists = JournalEntry.objects.filter(user=self.user, title='New Entry').exists()
        self.assertTrue(entry_exists)
    
    def test_entry_detail_loads(self):
        """Entry detail page loads."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Detail Entry',
            body='Content to view',
            entry_date=date.today()
        )
        response = self.client.get(
            reverse('journal:entry_detail', kwargs={'pk': entry.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Detail Entry')
    
    def test_entry_can_be_updated(self):
        """User can update their entry."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Original Title',
            body='Original content',
            entry_date=date.today()
        )
        
        response = self.client.post(
            reverse('journal:entry_update', kwargs={'pk': entry.pk}),
            {
                'title': 'Updated Title',
                'body': 'Updated content',
                'entry_date': date.today().isoformat(),
            }
        )
        
        entry.refresh_from_db()
        self.assertEqual(entry.title, 'Updated Title')
    
    def test_entry_can_be_deleted(self):
        """User can delete their entry."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Delete Me',
            body='Content',
            entry_date=date.today()
        )
        
        response = self.client.post(
            reverse('journal:entry_delete', kwargs={'pk': entry.pk})
        )
        
        self.assertFalse(JournalEntry.objects.filter(pk=entry.pk).exists())


class JournalDataIsolationTest(TestCase):
    """Tests to ensure users can only see their own journal entries."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='usera@example.com',
            password='testpass123'
        )
        self.user_b = User.objects.create_user(
            email='userb@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user_a)
        self._accept_terms(self.user_b)
        
        # Create entries for each user
        self.entry_a = JournalEntry.objects.create(
            user=self.user_a,
            title='User A Entry',
            body='Private content A',
            entry_date=date.today()
        )
        self.entry_b = JournalEntry.objects.create(
            user=self.user_b,
            title='User B Entry',
            body='Private content B',
            entry_date=date.today()
        )
    
    def _accept_terms(self, user):
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass
    
    def test_user_a_sees_only_their_entries(self):
        """User A only sees their own entries."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('journal:entry_list'))
        
        self.assertContains(response, 'User A Entry')
        self.assertNotContains(response, 'User B Entry')
    
    def test_user_cannot_view_other_users_entry(self):
        """User A cannot view User B's entry."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('journal:entry_detail', kwargs={'pk': self.entry_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_edit_other_users_entry(self):
        """User A cannot edit User B's entry."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('journal:entry_update', kwargs={'pk': self.entry_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_entry(self):
        """User A cannot delete User B's entry."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('journal:entry_delete', kwargs={'pk': self.entry_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(JournalEntry.objects.filter(pk=self.entry_b.pk).exists())