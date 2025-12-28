"""
Saved Verses Tests

Tests for user-specific saved Scripture verses feature.
Ensures each user has their own private Scripture library.

Location: apps/faith/tests/test_saved_verses.py
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.faith.models import SavedVerse, ScriptureVerse
from apps.users.models import TermsAcceptance

User = get_user_model()


def accept_terms(user):
    """Accept terms of service for user."""
    TermsAcceptance.objects.get_or_create(
        user=user,
        defaults={'terms_version': '1.0'}
    )


def setup_user_for_faith(user):
    """Configure user for faith module access."""
    user.preferences.faith_enabled = True
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    accept_terms(user)


class SavedVerseModelTest(TestCase):
    """Tests for the SavedVerse model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        setup_user_for_faith(self.user)

    def test_saved_verse_belongs_to_user(self):
        """SavedVerse has a user field."""
        verse = SavedVerse.objects.create(
            user=self.user,
            reference='John 3:16',
            text='For God so loved the world...',
            translation='ESV',
            book_name='John',
            book_order=43,
            chapter=3,
            verse_start=16,
            themes=['love', 'salvation']
        )
        self.assertEqual(verse.user, self.user)

    def test_saved_verse_str(self):
        """Saved verse string includes reference and translation."""
        verse = SavedVerse.objects.create(
            user=self.user,
            reference='Psalm 23:1',
            text='The Lord is my shepherd...',
            translation='NIV',
            book_name='Psalms',
            book_order=19,
            chapter=23,
            verse_start=1
        )
        self.assertIn('Psalm 23:1', str(verse))
        self.assertIn('NIV', str(verse))

    def test_saved_verse_with_notes(self):
        """Saved verse can have personal notes."""
        verse = SavedVerse.objects.create(
            user=self.user,
            reference='Romans 8:28',
            text='And we know that in all things God works...',
            translation='NIV',
            book_name='Romans',
            book_order=45,
            chapter=8,
            verse_start=28,
            notes='This verse helped me during a difficult time.'
        )
        self.assertEqual(verse.notes, 'This verse helped me during a difficult time.')


class SavedVerseDataIsolationTest(TestCase):
    """Tests for data isolation between users."""

    def setUp(self):
        # Create two users
        self.user_a = User.objects.create_user(
            email='user_a@example.com',
            password='testpass123'
        )
        setup_user_for_faith(self.user_a)

        self.user_b = User.objects.create_user(
            email='user_b@example.com',
            password='testpass123'
        )
        setup_user_for_faith(self.user_b)

        # Create saved verses for each user
        self.verse_a = SavedVerse.objects.create(
            user=self.user_a,
            reference='John 3:16',
            text='For God so loved the world...',
            translation='ESV',
            book_name='John',
            book_order=43,
            chapter=3,
            verse_start=16
        )

        self.verse_b = SavedVerse.objects.create(
            user=self.user_b,
            reference='Psalm 23:1',
            text='The Lord is my shepherd...',
            translation='NIV',
            book_name='Psalms',
            book_order=19,
            chapter=23,
            verse_start=1
        )

        self.client = Client()

    def test_user_a_only_sees_own_saved_verses(self):
        """User A only sees their own saved verses."""
        self.client.login(email='user_a@example.com', password='testpass123')
        response = self.client.get(reverse('faith:scripture_list'))

        # Should see their own verse
        self.assertContains(response, 'John 3:16')
        # Should NOT see User B's verse
        self.assertNotContains(response, 'Psalm 23:1')

    def test_user_b_only_sees_own_saved_verses(self):
        """User B only sees their own saved verses."""
        self.client.login(email='user_b@example.com', password='testpass123')
        response = self.client.get(reverse('faith:scripture_list'))

        # Should see their own verse
        self.assertContains(response, 'Psalm 23:1')
        # Should NOT see User A's verse
        self.assertNotContains(response, 'John 3:16')

    def test_new_user_sees_empty_library(self):
        """New user has empty saved verses library."""
        new_user = User.objects.create_user(
            email='new_user@example.com',
            password='testpass123'
        )
        setup_user_for_faith(new_user)

        self.client.login(email='new_user@example.com', password='testpass123')
        response = self.client.get(reverse('faith:scripture_list'))

        # Should see empty state message
        self.assertContains(response, 'No saved verses yet')


class SavedVerseSaveViewTest(TestCase):
    """Tests for saving verses to user's library."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        setup_user_for_faith(self.user)
        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_save_verse_assigns_to_current_user(self):
        """Saving a verse assigns it to the current user."""
        response = self.client.post(reverse('faith:scripture_save'), {
            'reference': 'Philippians 4:13',
            'text': 'I can do all things through Christ who strengthens me.',
            'book_name': 'Philippians',
            'chapter': '4',
            'verse_start': '13',
            'verse_end': '',
            'translation': 'NKJV - New King James Version',
            'themes': 'strength, faith',
            'notes': ''
        })

        # Should redirect after saving
        self.assertEqual(response.status_code, 302)

        # Verse should exist and belong to user
        verse = SavedVerse.objects.get(reference='Philippians 4:13')
        self.assertEqual(verse.user, self.user)

    def test_saved_verse_not_visible_to_other_users(self):
        """Saved verse is not visible to other users."""
        # User A saves a verse
        self.client.post(reverse('faith:scripture_save'), {
            'reference': 'Jeremiah 29:11',
            'text': 'For I know the plans I have for you...',
            'book_name': 'Jeremiah',
            'chapter': '29',
            'verse_start': '11',
            'verse_end': '',
            'translation': 'NIV',
            'themes': 'hope, future',
            'notes': ''
        })

        # Verify verse was created for User A
        self.assertEqual(SavedVerse.objects.filter(user=self.user, reference='Jeremiah 29:11').count(), 1)

        # Create and login as User B
        user_b = User.objects.create_user(
            email='user_b@example.com',
            password='testpass123'
        )
        setup_user_for_faith(user_b)

        # Verify User B has no saved verses
        self.assertEqual(SavedVerse.objects.filter(user=user_b).count(), 0)

        # Verify the verse doesn't belong to User B
        self.assertEqual(SavedVerse.objects.filter(user=user_b, reference='Jeremiah 29:11').count(), 0)

    def test_save_verse_with_themes(self):
        """Saved verse correctly parses themes."""
        self.client.post(reverse('faith:scripture_save'), {
            'reference': 'Proverbs 3:5-6',
            'text': 'Trust in the Lord with all your heart...',
            'book_name': 'Proverbs',
            'chapter': '3',
            'verse_start': '5',
            'verse_end': '6',
            'translation': 'ESV',
            'themes': 'trust, guidance, wisdom',
            'notes': ''
        })

        verse = SavedVerse.objects.get(reference='Proverbs 3:5-6')
        self.assertEqual(verse.themes, ['trust', 'guidance', 'wisdom'])

    def test_save_verse_with_notes(self):
        """Saved verse correctly saves personal notes."""
        self.client.post(reverse('faith:scripture_save'), {
            'reference': 'Isaiah 40:31',
            'text': 'But those who hope in the Lord will renew their strength...',
            'book_name': 'Isaiah',
            'chapter': '40',
            'verse_start': '31',
            'verse_end': '',
            'translation': 'NIV',
            'themes': 'strength, hope',
            'notes': 'My favorite verse for difficult times.'
        })

        verse = SavedVerse.objects.get(reference='Isaiah 40:31')
        self.assertEqual(verse.notes, 'My favorite verse for difficult times.')


class SavedVerseFilterTest(TestCase):
    """Tests for filtering saved verses."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        setup_user_for_faith(self.user)

        # Create multiple saved verses with different themes/books
        SavedVerse.objects.create(
            user=self.user,
            reference='John 3:16',
            text='For God so loved the world...',
            translation='ESV',
            book_name='John',
            book_order=43,
            chapter=3,
            verse_start=16,
            themes=['love', 'salvation']
        )
        SavedVerse.objects.create(
            user=self.user,
            reference='John 14:6',
            text='I am the way, the truth, and the life...',
            translation='ESV',
            book_name='John',
            book_order=43,
            chapter=14,
            verse_start=6,
            themes=['truth', 'salvation']
        )
        SavedVerse.objects.create(
            user=self.user,
            reference='Psalm 23:1',
            text='The Lord is my shepherd...',
            translation='NIV',
            book_name='Psalms',
            book_order=19,
            chapter=23,
            verse_start=1,
            themes=['peace', 'trust']
        )

        self.client = Client()
        self.client.login(email='test@example.com', password='testpass123')

    def test_filter_by_book(self):
        """Filter saved verses by book name."""
        response = self.client.get(reverse('faith:scripture_list'), {'book': 'John'})

        self.assertContains(response, 'John 3:16')
        self.assertContains(response, 'John 14:6')
        self.assertNotContains(response, 'Psalm 23:1')

    def test_filter_by_theme(self):
        """Filter saved verses by theme."""
        response = self.client.get(reverse('faith:scripture_list'), {'theme': 'salvation'})

        self.assertContains(response, 'John 3:16')
        self.assertContains(response, 'John 14:6')
        self.assertNotContains(response, 'Psalm 23:1')

    def test_available_themes_from_user_verses_only(self):
        """Available themes filter only shows themes from user's verses."""
        # Create another user with different themes
        other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123'
        )
        setup_user_for_faith(other_user)
        SavedVerse.objects.create(
            user=other_user,
            reference='Romans 8:28',
            text='And we know that in all things...',
            translation='NIV',
            book_name='Romans',
            book_order=45,
            chapter=8,
            verse_start=28,
            themes=['xyzuniquetheme', 'abcspecialtheme']  # Unique themes that won't appear elsewhere
        )

        response = self.client.get(reverse('faith:scripture_list'))
        content = response.content.decode()

        # User's themes should be in filter dropdown
        self.assertIn('love', content)
        self.assertIn('salvation', content)
        self.assertIn('peace', content)
        self.assertIn('trust', content)

        # Other user's unique themes should NOT be in filter dropdown
        self.assertNotIn('xyzuniquetheme', content)
        self.assertNotIn('abcspecialtheme', content)
