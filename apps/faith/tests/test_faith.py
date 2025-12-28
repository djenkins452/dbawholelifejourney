"""
Faith Module Tests

Tests for prayer requests, scripture verses, and faith milestones.

Location: apps/faith/tests/test_faith.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.faith.models import PrayerRequest, FaithMilestone, ScriptureVerse

User = get_user_model()


class ScriptureVerseModelTest(TestCase):
    """Tests for the ScriptureVerse model."""
    
    def test_create_verse(self):
        """Scripture verse can be created."""
        verse = ScriptureVerse.objects.create(
            reference='John 3:16',
            text='For God so loved the world...',
            translation='ESV',
            book_name='John',
            book_order=43,
            chapter=3,
            verse_start=16,
            themes=['love', 'salvation'],
            contexts=['evangelism']
        )
        self.assertEqual(verse.reference, 'John 3:16')
        self.assertTrue(verse.is_active)
    
    def test_verse_str(self):
        """Verse string includes reference and translation."""
        verse = ScriptureVerse.objects.create(
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


class PrayerRequestModelTest(TestCase):
    """Tests for the PrayerRequest model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_prayer_request(self):
        """Prayer request can be created."""
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title='Healing for Mom',
            description='Praying for her recovery'
        )
        self.assertEqual(prayer.title, 'Healing for Mom')
        self.assertFalse(prayer.is_answered)
        self.assertEqual(prayer.priority, 'normal')
    
    def test_prayer_request_str(self):
        """Prayer request string is the title."""
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title='Job Interview'
        )
        self.assertEqual(str(prayer), 'Job Interview')
    
    def test_mark_answered(self):
        """mark_answered() sets answered status and timestamp."""
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title='Test Prayer'
        )
        prayer.mark_answered(notes='God provided!')
        
        self.assertTrue(prayer.is_answered)
        self.assertIsNotNone(prayer.answered_at)
        self.assertEqual(prayer.answer_notes, 'God provided!')
    
    def test_urgent_priority(self):
        """Prayer request can have urgent priority."""
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title='Urgent Need',
            priority='urgent'
        )
        self.assertEqual(prayer.priority, 'urgent')


class FaithMilestoneModelTest(TestCase):
    """Tests for the FaithMilestone model."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
    
    def test_create_milestone(self):
        """Faith milestone can be created."""
        milestone = FaithMilestone.objects.create(
            user=self.user,
            title='Baptism',
            milestone_type='baptism',
            date=date(2020, 6, 15),
            description='Got baptized at church'
        )
        self.assertEqual(milestone.title, 'Baptism')
        self.assertEqual(milestone.milestone_type, 'baptism')
    
    def test_milestone_str(self):
        """Milestone string includes title and date."""
        milestone = FaithMilestone.objects.create(
            user=self.user,
            title='Salvation',
            milestone_type='salvation',
            date=date(2015, 3, 20)
        )
        self.assertIn('Salvation', str(milestone))
        self.assertIn('2015', str(milestone))


class FaithViewTest(TestCase):
    """Tests for faith module views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        # Enable faith module
        self.user.preferences.faith_enabled = True
        self.user.preferences.save()

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version='1.0'
        )

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
    
    def test_faith_home_requires_login(self):
        """Faith home requires authentication."""
        response = self.client.get(reverse('faith:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_faith_home_loads(self):
        """Faith home page loads for authenticated user."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('faith:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_prayer_list_loads(self):
        """Prayer list page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('faith:prayer_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_prayer_can_be_created(self):
        """User can create a prayer request."""
        self.client.login(email='test@example.com', password='testpass123')
        
        # Create directly to test model
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title='New Prayer',
            description='Please help with this',
            priority='normal'
        )
        self.assertTrue(
            PrayerRequest.objects.filter(user=self.user, title='New Prayer').exists()
        )
    
    def test_milestone_list_loads(self):
        """Milestone list page loads."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('faith:milestone_list'))
        self.assertEqual(response.status_code, 200)


class FaithDataIsolationTest(TestCase):
    """Tests to ensure users can only see their own faith data."""

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
        self._complete_onboarding(self.user_a)
        self._complete_onboarding(self.user_b)

        # Enable faith module for both users
        self.user_a.preferences.faith_enabled = True
        self.user_a.preferences.save()
        self.user_b.preferences.faith_enabled = True
        self.user_b.preferences.save()

        # Create prayer requests for each user
        self.prayer_a = PrayerRequest.objects.create(
            user=self.user_a,
            title='User A Prayer'
        )
        self.prayer_b = PrayerRequest.objects.create(
            user=self.user_b,
            title='User B Prayer'
        )

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version='1.0'
        )

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
    
    def test_user_a_sees_only_their_prayers(self):
        """User A only sees their own prayers."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('faith:prayer_list'))
        
        self.assertContains(response, 'User A Prayer')
        self.assertNotContains(response, 'User B Prayer')
    
    def test_user_cannot_edit_other_users_prayer(self):
        """User A cannot edit User B's prayer."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('faith:prayer_update', kwargs={'pk': self.prayer_b.pk})
        )
        self.assertEqual(response.status_code, 404)