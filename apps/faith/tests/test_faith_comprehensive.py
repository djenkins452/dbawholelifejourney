"""
Faith Module - Comprehensive Tests

This test file covers:
1. Model tests (CRUD, validation, properties, methods)
2. View tests (loading, authentication, context)
3. Form validation tests
4. Edge case tests
5. Business logic tests (answered prayers, milestones)
6. Integration tests
7. Permission/data isolation tests
8. Scripture verse tests

Location: apps/faith/tests/test_faith_comprehensive.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.faith.models import PrayerRequest, FaithMilestone, ScriptureVerse

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class FaithTestMixin:
    """Common setup for faith tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted, onboarding completed, and faith enabled."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        self._enable_faith(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def _enable_faith(self, user):
        user.preferences.faith_enabled = True
        user.preferences.save()
    
    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)
    
    def create_prayer(self, user, title='Test Prayer', **kwargs):
        """Helper to create a prayer request."""
        return PrayerRequest.objects.create(user=user, title=title, **kwargs)
    
    def create_milestone(self, user, title='Test Milestone', **kwargs):
        """Helper to create a faith milestone."""
        defaults = {
            'milestone_type': 'other',
            'date': date.today(),
        }
        defaults.update(kwargs)
        return FaithMilestone.objects.create(user=user, title=title, **defaults)
    
    def create_verse(self, reference='John 3:16', **kwargs):
        """Helper to create a scripture verse."""
        defaults = {
            'text': 'For God so loved the world...',
            'translation': 'ESV',
            'book_name': 'John',
            'book_order': 43,
            'chapter': 3,
            'verse_start': 16,
        }
        defaults.update(kwargs)
        return ScriptureVerse.objects.create(reference=reference, **defaults)


# =============================================================================
# 1. SCRIPTURE VERSE MODEL TESTS
# =============================================================================

class ScriptureVerseModelTest(FaithTestMixin, TestCase):
    """Tests for the ScriptureVerse model."""
    
    def test_create_verse(self):
        """Scripture verse can be created."""
        verse = self.create_verse()
        self.assertEqual(verse.reference, 'John 3:16')
        self.assertTrue(verse.is_active)
    
    def test_verse_with_all_fields(self):
        """Verse can be created with all fields."""
        verse = ScriptureVerse.objects.create(
            reference='Philippians 4:6-7',
            text='Do not be anxious about anything...',
            translation='NIV',
            book_name='Philippians',
            book_order=50,
            chapter=4,
            verse_start=6,
            verse_end=7,
            themes=['peace', 'anxiety', 'prayer'],
            contexts=['worry', 'stress'],
            is_active=True
        )
        self.assertEqual(verse.verse_end, 7)
        self.assertIn('peace', verse.themes)
    
    def test_verse_str(self):
        """Verse string includes reference and translation."""
        verse = self.create_verse(reference='Psalm 23:1', translation='NIV')
        str_repr = str(verse)
        self.assertIn('Psalm 23:1', str_repr)
        self.assertIn('NIV', str_repr)
    
    def test_verse_ordering(self):
        """Verses are ordered by book order, chapter, verse."""
        verse_later = self.create_verse(
            reference='Romans 8:28',
            book_name='Romans',
            book_order=45,
            chapter=8,
            verse_start=28
        )
        verse_earlier = self.create_verse(
            reference='Genesis 1:1',
            book_name='Genesis',
            book_order=1,
            chapter=1,
            verse_start=1
        )
        
        verses = ScriptureVerse.objects.all()
        self.assertEqual(verses[0], verse_earlier)
    
    def test_filter_active_verses(self):
        """Can filter to only active verses."""
        active = self.create_verse(reference='Active', is_active=True)
        inactive = self.create_verse(reference='Inactive', is_active=False)
        
        active_verses = ScriptureVerse.objects.filter(is_active=True)
        self.assertEqual(active_verses.count(), 1)
    
    def test_filter_by_theme(self):
        """Can filter verses by theme (using Python filtering for SQLite compatibility)."""
        peace_verse = self.create_verse(
            reference='Peace Verse',
            themes=['peace', 'comfort']
        )
        strength_verse = self.create_verse(
            reference='Strength Verse',
            themes=['strength', 'courage']
        )
        
        # Filter in Python since SQLite doesn't support JSON contains
        all_verses = ScriptureVerse.objects.all()
        peace_verses = [v for v in all_verses if 'peace' in v.themes]
        self.assertEqual(len(peace_verses), 1)
    
    def test_translation_choices(self):
        """Verse supports multiple translations."""
        translations = ['ESV', 'NIV', 'BSB', 'NKJV', 'NLT']
        for trans in translations:
            verse = self.create_verse(
                reference=f'{trans} Verse',
                translation=trans
            )
            self.assertEqual(verse.translation, trans)


# =============================================================================
# 2. PRAYER REQUEST MODEL TESTS
# =============================================================================

class PrayerRequestModelTest(FaithTestMixin, TestCase):
    """Tests for the PrayerRequest model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_prayer(self):
        """Prayer request can be created."""
        prayer = self.create_prayer(self.user)
        self.assertEqual(prayer.title, 'Test Prayer')
        self.assertFalse(prayer.is_answered)
    
    def test_prayer_default_values(self):
        """Prayer has correct default values."""
        prayer = self.create_prayer(self.user)
        self.assertEqual(prayer.priority, 'normal')
        self.assertFalse(prayer.is_answered)
        self.assertFalse(prayer.remind_daily)
        self.assertTrue(prayer.is_personal)
    
    def test_prayer_str(self):
        """Prayer string is the title."""
        prayer = self.create_prayer(self.user, title='Healing Prayer')
        self.assertEqual(str(prayer), 'Healing Prayer')
    
    def test_mark_answered(self):
        """mark_answered() sets status and timestamp."""
        prayer = self.create_prayer(self.user)
        prayer.mark_answered(notes='God provided!')
        
        self.assertTrue(prayer.is_answered)
        self.assertIsNotNone(prayer.answered_at)
        self.assertEqual(prayer.answer_notes, 'God provided!')
    
    def test_mark_answered_without_notes(self):
        """mark_answered() works without notes."""
        prayer = self.create_prayer(self.user)
        prayer.mark_answered()
        
        self.assertTrue(prayer.is_answered)
        self.assertEqual(prayer.answer_notes, '')
    
    def test_urgent_priority(self):
        """Prayer can have urgent priority."""
        prayer = self.create_prayer(self.user, priority='urgent')
        self.assertEqual(prayer.priority, 'urgent')
    
    def test_prayer_for_others(self):
        """Prayer can be for others (not personal)."""
        prayer = self.create_prayer(
            self.user,
            is_personal=False,
            person_or_situation='Mom\'s health'
        )
        self.assertFalse(prayer.is_personal)
        self.assertEqual(prayer.person_or_situation, "Mom's health")
    
    def test_daily_reminder(self):
        """Prayer can be set for daily reminder."""
        prayer = self.create_prayer(self.user, remind_daily=True)
        self.assertTrue(prayer.remind_daily)
    
    def test_ordering_by_created_at(self):
        """Prayers are ordered by most recent first."""
        old_prayer = self.create_prayer(self.user, title='Old')
        new_prayer = self.create_prayer(self.user, title='New')
        
        prayers = PrayerRequest.objects.filter(user=self.user)
        self.assertEqual(prayers[0], new_prayer)


# =============================================================================
# 3. FAITH MILESTONE MODEL TESTS
# =============================================================================

class FaithMilestoneModelTest(FaithTestMixin, TestCase):
    """Tests for the FaithMilestone model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_milestone(self):
        """Milestone can be created."""
        milestone = self.create_milestone(self.user)
        self.assertEqual(milestone.title, 'Test Milestone')
    
    def test_milestone_types(self):
        """Milestone supports different types."""
        types = ['salvation', 'baptism', 'rededication', 'answered_prayer', 
                 'spiritual_insight', 'community', 'other']
        
        for mtype in types:
            milestone = self.create_milestone(
                self.user,
                title=f'{mtype} milestone',
                milestone_type=mtype
            )
            self.assertEqual(milestone.milestone_type, mtype)
    
    def test_milestone_str(self):
        """Milestone string includes title and date."""
        milestone = self.create_milestone(
            self.user,
            title='My Baptism',
            date=date(2020, 6, 15)
        )
        str_repr = str(milestone)
        self.assertIn('My Baptism', str_repr)
        self.assertIn('2020', str_repr)
    
    def test_milestone_with_scripture(self):
        """Milestone can include scripture reference."""
        milestone = self.create_milestone(
            self.user,
            scripture_reference='Romans 6:4'
        )
        self.assertEqual(milestone.scripture_reference, 'Romans 6:4')
    
    def test_ordering_by_date(self):
        """Milestones are ordered by date descending."""
        old = self.create_milestone(
            self.user,
            title='Old',
            date=date(2020, 1, 1)
        )
        new = self.create_milestone(
            self.user,
            title='New',
            date=date(2024, 1, 1)
        )
        
        milestones = FaithMilestone.objects.filter(user=self.user)
        self.assertEqual(milestones[0], new)


# =============================================================================
# 4. VIEW TESTS - Basic Loading
# =============================================================================

class FaithViewBasicTest(FaithTestMixin, TestCase):
    """Basic view loading tests."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
    
    # --- Authentication Required ---
    
    def test_faith_home_requires_login(self):
        """Faith home redirects anonymous users."""
        response = self.client.get(reverse('faith:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_prayer_list_requires_login(self):
        """Prayer list requires authentication."""
        response = self.client.get(reverse('faith:prayer_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_milestone_list_requires_login(self):
        """Milestone list requires authentication."""
        response = self.client.get(reverse('faith:milestone_list'))
        self.assertEqual(response.status_code, 302)
    
    # --- Authenticated Access ---
    
    def test_faith_home_loads(self):
        """Faith home loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('faith:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_prayer_list_loads(self):
        """Prayer list page loads."""
        self.login_user()
        response = self.client.get(reverse('faith:prayer_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_prayer_create_loads(self):
        """Prayer create page loads."""
        self.login_user()
        response = self.client.get(reverse('faith:prayer_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_milestone_list_loads(self):
        """Milestone list page loads."""
        self.login_user()
        response = self.client.get(reverse('faith:milestone_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_milestone_create_loads(self):
        """Milestone create page loads."""
        self.login_user()
        response = self.client.get(reverse('faith:milestone_create'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. FORM VALIDATION TESTS
# =============================================================================

class FaithFormTest(FaithTestMixin, TestCase):
    """Tests for faith form validation."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_create_prayer_with_valid_data(self):
        """Prayer can be created with valid data."""
        response = self.client.post(reverse('faith:prayer_create'), {
            'title': 'New Prayer Request',
            'description': 'Please help with this situation',
            'priority': 'normal',
            'is_personal': True,
        })
        
        self.assertTrue(
            PrayerRequest.objects.filter(title='New Prayer Request').exists()
        )
    
    def test_create_milestone_with_valid_data(self):
        """Milestone can be created with valid data."""
        response = self.client.post(reverse('faith:milestone_create'), {
            'title': 'My Baptism',
            'milestone_type': 'baptism',
            'date': '2020-06-15',
            'description': 'Got baptized at my church',
        })
        
        self.assertTrue(
            FaithMilestone.objects.filter(title='My Baptism').exists()
        )
    
    def test_update_prayer(self):
        """Prayer can be updated."""
        prayer = self.create_prayer(self.user, title='Original')
        
        response = self.client.post(
            reverse('faith:prayer_update', kwargs={'pk': prayer.pk}),
            {
                'title': 'Updated Prayer',
                'priority': 'urgent',
                'is_personal': True,
            }
        )
        
        prayer.refresh_from_db()
        self.assertEqual(prayer.title, 'Updated Prayer')
        self.assertEqual(prayer.priority, 'urgent')


# =============================================================================
# 6. EDGE CASE TESTS
# =============================================================================

class FaithEdgeCaseTest(FaithTestMixin, TestCase):
    """Tests for edge cases."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_prayer_list_empty(self):
        """Prayer list loads with no prayers."""
        response = self.client.get(reverse('faith:prayer_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_milestone_list_empty(self):
        """Milestone list loads with no milestones."""
        response = self.client.get(reverse('faith:milestone_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_long_prayer_title(self):
        """Prayer handles long title."""
        long_title = 'A' * 200
        prayer = self.create_prayer(self.user, title=long_title)
        self.assertEqual(prayer.title, long_title)
    
    def test_prayer_with_special_characters(self):
        """Prayer handles special characters."""
        title = "Mom's healing & Dad's job <test>"
        prayer = self.create_prayer(self.user, title=title)
        self.assertEqual(prayer.title, title)
    
    def test_milestone_with_old_date(self):
        """Milestone can have very old date."""
        old_date = date(1990, 1, 1)
        milestone = self.create_milestone(self.user, date=old_date)
        self.assertEqual(milestone.date, old_date)
    
    def test_verse_with_empty_themes(self):
        """Verse handles empty themes list."""
        verse = self.create_verse(themes=[])
        self.assertEqual(verse.themes, [])


# =============================================================================
# 7. BUSINESS LOGIC TESTS
# =============================================================================

class FaithBusinessLogicTest(FaithTestMixin, TestCase):
    """Tests for business logic."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_filter_answered_prayers(self):
        """Can filter answered prayers."""
        unanswered = self.create_prayer(self.user, title='Unanswered')
        answered = self.create_prayer(self.user, title='Answered')
        answered.mark_answered()
        
        answered_prayers = PrayerRequest.objects.filter(
            user=self.user, is_answered=True
        )
        self.assertEqual(answered_prayers.count(), 1)
        self.assertEqual(answered_prayers.first().title, 'Answered')
    
    def test_filter_urgent_prayers(self):
        """Can filter urgent prayers."""
        normal = self.create_prayer(self.user, priority='normal')
        urgent = self.create_prayer(self.user, priority='urgent')
        
        urgent_prayers = PrayerRequest.objects.filter(
            user=self.user, priority='urgent'
        )
        self.assertEqual(urgent_prayers.count(), 1)
    
    def test_filter_daily_reminder_prayers(self):
        """Can filter prayers with daily reminders."""
        regular = self.create_prayer(self.user, remind_daily=False)
        daily = self.create_prayer(self.user, remind_daily=True)
        
        daily_prayers = PrayerRequest.objects.filter(
            user=self.user, remind_daily=True
        )
        self.assertEqual(daily_prayers.count(), 1)
    
    def test_milestones_by_type(self):
        """Can filter milestones by type."""
        baptism = self.create_milestone(
            self.user, title='Baptism', milestone_type='baptism'
        )
        salvation = self.create_milestone(
            self.user, title='Salvation', milestone_type='salvation'
        )
        
        baptisms = FaithMilestone.objects.filter(
            user=self.user, milestone_type='baptism'
        )
        self.assertEqual(baptisms.count(), 1)


# =============================================================================
# 8. DATA ISOLATION TESTS
# =============================================================================

class FaithDataIsolationTest(FaithTestMixin, TestCase):
    """Tests to ensure users can only see their own faith data."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')
        
        self.prayer_a = self.create_prayer(self.user_a, title='User A Prayer')
        self.prayer_b = self.create_prayer(self.user_b, title='User B Prayer')
        
        self.milestone_a = self.create_milestone(
            self.user_a, title='User A Milestone'
        )
        self.milestone_b = self.create_milestone(
            self.user_b, title='User B Milestone'
        )
    
    def test_user_sees_only_own_prayers(self):
        """User only sees their own prayers."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('faith:prayer_list'))
        
        self.assertContains(response, 'User A Prayer')
        self.assertNotContains(response, 'User B Prayer')
    
    def test_user_sees_only_own_milestones(self):
        """User only sees their own milestones."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('faith:milestone_list'))
        
        self.assertContains(response, 'User A Milestone')
        self.assertNotContains(response, 'User B Milestone')
    
    def test_user_cannot_view_other_users_prayer(self):
        """User cannot view another user's prayer detail."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('faith:prayer_detail', kwargs={'pk': self.prayer_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_edit_other_users_prayer(self):
        """User cannot edit another user's prayer."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('faith:prayer_update', kwargs={'pk': self.prayer_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_prayer(self):
        """User cannot delete another user's prayer."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('faith:prayer_delete', kwargs={'pk': self.prayer_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(PrayerRequest.objects.filter(pk=self.prayer_b.pk).exists())
    
    def test_user_cannot_edit_other_users_milestone(self):
        """User cannot edit another user's milestone."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('faith:milestone_update', kwargs={'pk': self.milestone_b.pk})
        )
        self.assertEqual(response.status_code, 404)


# =============================================================================
# 9. CONTEXT TESTS
# =============================================================================

class FaithContextTest(FaithTestMixin, TestCase):
    """Tests for view context data."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_prayer_list_has_prayers(self):
        """Prayer list includes prayers in context."""
        self.create_prayer(self.user)
        
        response = self.client.get(reverse('faith:prayer_list'))
        
        # Check for object_list or prayers in context
        self.assertTrue(
            'object_list' in response.context or 'prayers' in response.context
        )
    
    def test_milestone_list_has_milestones(self):
        """Milestone list includes milestones in context."""
        self.create_milestone(self.user)
        
        response = self.client.get(reverse('faith:milestone_list'))
        
        self.assertTrue(
            'object_list' in response.context or 'milestones' in response.context
        )
    
    def test_prayer_create_has_form(self):
        """Prayer create includes form in context."""
        response = self.client.get(reverse('faith:prayer_create'))
        
        self.assertIn('form', response.context)


# =============================================================================
# 10. MODULE DISABLED TESTS
# =============================================================================

class FaithModuleDisabledTest(TestCase):
    """Tests for when faith module is disabled."""
    
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        # Accept terms but DON'T enable faith
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=self.user, terms_version='1.0')
        self.user.preferences.faith_enabled = False
        self.user.preferences.save()
    
    def test_faith_home_redirects_when_disabled(self):
        """Faith home redirects when module is disabled."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('faith:home'))
        
        # Should redirect (302) when module is disabled
        self.assertEqual(response.status_code, 302)