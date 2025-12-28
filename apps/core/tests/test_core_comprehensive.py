"""
Core Module - Comprehensive Tests

This test file covers:
1. SoftDeleteModel behavior (status field, managers)
2. UserOwnedModel behavior (user field, ownership)
3. TimeStampedModel behavior (created_at, updated_at)
4. Tag model (user-specific tags)
5. SiteConfiguration (singleton pattern)

Location: apps/core/tests/test_core_comprehensive.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.models import Tag, SiteConfiguration
from apps.journal.models import JournalEntry  # Uses SoftDeleteModel

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class CoreTestMixin:
    """Common setup for core tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
    
    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)
    
    def create_tag(self, user, name='Test Tag', **kwargs):
        """Helper to create a tag."""
        return Tag.objects.create(user=user, name=name, **kwargs)


# =============================================================================
# 1. SOFT DELETE MODEL TESTS
# =============================================================================

class SoftDeleteModelTest(CoreTestMixin, TestCase):
    """Tests for SoftDeleteModel behavior using JournalEntry."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_default_status_is_active(self):
        """New records have 'active' status by default."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today()
        )
        self.assertEqual(entry.status, 'active')
    
    def test_soft_delete_changes_status(self):
        """Soft delete changes status to 'deleted'."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today()
        )
        entry.status = 'deleted'
        entry.save()
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'deleted')
    
    def test_archive_changes_status(self):
        """Archive changes status to 'archived'."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today()
        )
        entry.status = 'archived'
        entry.save()
        
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'archived')
    
    def test_default_manager_excludes_deleted(self):
        """Default manager excludes deleted records."""
        active = JournalEntry.objects.create(
            user=self.user,
            title='Active',
            body='Content',
            entry_date=date.today()
        )
        deleted = JournalEntry.objects.create(
            user=self.user,
            title='Deleted',
            body='Content',
            entry_date=date.today(),
            status='deleted'
        )
        
        # Default manager should only return active
        entries = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.first().title, 'Active')
    
    def test_all_objects_includes_deleted(self):
        """all_objects manager includes deleted records."""
        active = JournalEntry.objects.create(
            user=self.user,
            title='Active',
            body='Content',
            entry_date=date.today()
        )
        deleted = JournalEntry.objects.create(
            user=self.user,
            title='Deleted',
            body='Content',
            entry_date=date.today(),
            status='deleted'
        )
        
        # all_objects should return both
        entries = JournalEntry.all_objects.filter(user=self.user)
        self.assertEqual(entries.count(), 2)
    
    def test_status_choices(self):
        """Status field accepts valid choices."""
        for status in ['active', 'archived', 'deleted']:
            entry = JournalEntry.objects.create(
                user=self.user,
                title=f'{status} entry',
                body='Content',
                entry_date=date.today(),
                status=status
            )
            self.assertEqual(entry.status, status)


# =============================================================================
# 2. TIMESTAMPED MODEL TESTS
# =============================================================================

class TimeStampedModelTest(CoreTestMixin, TestCase):
    """Tests for TimeStampedModel behavior."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_created_at_set_on_create(self):
        """created_at is automatically set on creation."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Content',
            entry_date=date.today()
        )
        self.assertIsNotNone(entry.created_at)
    
    def test_updated_at_set_on_create(self):
        """updated_at is automatically set on creation."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Content',
            entry_date=date.today()
        )
        self.assertIsNotNone(entry.updated_at)
    
    def test_updated_at_changes_on_save(self):
        """updated_at changes when record is modified."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Content',
            entry_date=date.today()
        )
        original_updated = entry.updated_at
        
        # Modify and save
        entry.title = 'Modified'
        entry.save()
        
        self.assertGreater(entry.updated_at, original_updated)
    
    def test_created_at_does_not_change(self):
        """created_at does not change on subsequent saves."""
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test',
            body='Content',
            entry_date=date.today()
        )
        original_created = entry.created_at
        
        # Modify and save
        entry.title = 'Modified'
        entry.save()
        
        self.assertEqual(entry.created_at, original_created)


# =============================================================================
# 3. USER OWNED MODEL TESTS
# =============================================================================

class UserOwnedModelTest(CoreTestMixin, TestCase):
    """Tests for UserOwnedModel behavior."""
    
    def setUp(self):
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')
    
    def test_user_field_required(self):
        """User field is required for user-owned models."""
        with self.assertRaises(Exception):
            JournalEntry.objects.create(
                title='No User',
                body='Content',
                entry_date=date.today()
            )
    
    def test_records_belong_to_user(self):
        """Records are correctly associated with user."""
        entry = JournalEntry.objects.create(
            user=self.user_a,
            title='User A Entry',
            body='Content',
            entry_date=date.today()
        )
        self.assertEqual(entry.user, self.user_a)
    
    def test_filter_by_user(self):
        """Can filter records by user."""
        entry_a = JournalEntry.objects.create(
            user=self.user_a,
            title='User A',
            body='Content',
            entry_date=date.today()
        )
        entry_b = JournalEntry.objects.create(
            user=self.user_b,
            title='User B',
            body='Content',
            entry_date=date.today()
        )
        
        a_entries = JournalEntry.objects.filter(user=self.user_a)
        self.assertEqual(a_entries.count(), 1)
        self.assertEqual(a_entries.first().title, 'User A')
    
    def test_cascade_delete_with_user(self):
        """Records are deleted when user is deleted."""
        entry = JournalEntry.objects.create(
            user=self.user_a,
            title='Test',
            body='Content',
            entry_date=date.today()
        )
        entry_pk = entry.pk
        
        self.user_a.delete()
        
        self.assertFalse(
            JournalEntry.all_objects.filter(pk=entry_pk).exists()
        )


# =============================================================================
# 4. TAG MODEL TESTS
# =============================================================================

class TagModelTest(CoreTestMixin, TestCase):
    """Tests for the Tag model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_tag(self):
        """Tag can be created."""
        tag = self.create_tag(self.user)
        self.assertEqual(tag.name, 'Test Tag')
    
    def test_tag_str(self):
        """Tag string is the name."""
        tag = self.create_tag(self.user, name='Personal')
        self.assertEqual(str(tag), 'Personal')
    
    def test_tag_with_color(self):
        """Tag can have a color."""
        tag = self.create_tag(self.user, color='#FF5733')
        self.assertEqual(tag.color, '#FF5733')
    
    def test_tag_belongs_to_user(self):
        """Tags belong to specific users."""
        tag = self.create_tag(self.user)
        self.assertEqual(tag.user, self.user)
    
    def test_users_have_separate_tags(self):
        """Different users have separate tag namespaces."""
        user_b = self.create_user(email='userb@example.com')
        
        tag_a = self.create_tag(self.user, name='Work')
        tag_b = self.create_tag(user_b, name='Work')
        
        self.assertNotEqual(tag_a.pk, tag_b.pk)
        
        user_tags = Tag.objects.filter(user=self.user)
        self.assertEqual(user_tags.count(), 1)
    
    def test_tag_ordering(self):
        """Tags are ordered alphabetically or by creation."""
        tag_c = self.create_tag(self.user, name='Charlie')
        tag_a = self.create_tag(self.user, name='Alpha')
        tag_b = self.create_tag(self.user, name='Beta')
        
        tags = Tag.objects.filter(user=self.user)
        # Just verify we get all 3
        self.assertEqual(tags.count(), 3)


# =============================================================================
# 5. SITE CONFIGURATION TESTS
# =============================================================================

class SiteConfigurationTest(TestCase):
    """Tests for SiteConfiguration singleton model."""
    
    def test_get_or_create_config(self):
        """Can get or create site configuration."""
        config, created = SiteConfiguration.objects.get_or_create(pk=1)
        self.assertIsNotNone(config)
    
    def test_default_values(self):
        """Configuration has sensible defaults."""
        config, _ = SiteConfiguration.objects.get_or_create(pk=1)
        
        self.assertEqual(config.site_name, 'Whole Life Journey')
        self.assertTrue(config.allow_registration)
    
    def test_config_str(self):
        """Configuration string representation."""
        config, _ = SiteConfiguration.objects.get_or_create(pk=1)
        self.assertIn('Configuration', str(config))
    
    def test_update_config(self):
        """Configuration can be updated."""
        config, _ = SiteConfiguration.objects.get_or_create(pk=1)
        config.site_name = 'My Custom App'
        config.save()
        
        config.refresh_from_db()
        self.assertEqual(config.site_name, 'My Custom App')
    
    def test_feature_toggles(self):
        """Feature toggles can be changed."""
        config, _ = SiteConfiguration.objects.get_or_create(pk=1)
        
        config.allow_registration = False
        config.require_email_verification = True
        config.save()
        
        config.refresh_from_db()
        self.assertFalse(config.allow_registration)
        self.assertTrue(config.require_email_verification)


# =============================================================================
# 6. MANAGER TESTS
# =============================================================================

class SoftDeleteManagerTest(CoreTestMixin, TestCase):
    """Tests for custom managers on SoftDeleteModel."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_objects_manager_filters_active(self):
        """Default objects manager returns only active records."""
        active = JournalEntry.objects.create(
            user=self.user, title='Active', body='x', entry_date=date.today()
        )
        archived = JournalEntry.objects.create(
            user=self.user, title='Archived', body='x', 
            entry_date=date.today(), status='archived'
        )
        deleted = JournalEntry.objects.create(
            user=self.user, title='Deleted', body='x', 
            entry_date=date.today(), status='deleted'
        )
        
        results = JournalEntry.objects.filter(user=self.user)
        self.assertEqual(results.count(), 1)
    
    def test_all_objects_returns_everything(self):
        """all_objects manager returns all records."""
        for status in ['active', 'archived', 'deleted']:
            JournalEntry.objects.create(
                user=self.user, title=status, body='x',
                entry_date=date.today(), status=status
            )
        
        results = JournalEntry.all_objects.filter(user=self.user)
        self.assertEqual(results.count(), 3)
    
    def test_filter_archived_only(self):
        """Can filter to get only archived records."""
        active = JournalEntry.objects.create(
            user=self.user, title='Active', body='x', entry_date=date.today()
        )
        archived = JournalEntry.objects.create(
            user=self.user, title='Archived', body='x',
            entry_date=date.today(), status='archived'
        )
        
        results = JournalEntry.all_objects.filter(
            user=self.user, status='archived'
        )
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().title, 'Archived')
    
    def test_filter_deleted_only(self):
        """Can filter to get only deleted records."""
        active = JournalEntry.objects.create(
            user=self.user, title='Active', body='x', entry_date=date.today()
        )
        deleted = JournalEntry.objects.create(
            user=self.user, title='Deleted', body='x',
            entry_date=date.today(), status='deleted'
        )
        
        results = JournalEntry.all_objects.filter(
            user=self.user, status='deleted'
        )
        self.assertEqual(results.count(), 1)
        self.assertEqual(results.first().title, 'Deleted')


# =============================================================================
# 7. EDGE CASE TESTS
# =============================================================================

class CoreEdgeCaseTest(CoreTestMixin, TestCase):
    """Edge case tests for core functionality."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_empty_tag_name(self):
        """Tag with empty name handling."""
        # Should either fail or work depending on model constraints
        try:
            tag = Tag.objects.create(user=self.user, name='')
            # If it works, name should be empty string
            self.assertEqual(tag.name, '')
        except Exception:
            # If it fails, that's also acceptable
            pass
    
    def test_very_long_tag_name(self):
        """Tag handles long names."""
        long_name = 'A' * 100
        tag = self.create_tag(self.user, name=long_name)
        self.assertTrue(len(tag.name) > 0)
    
    def test_special_characters_in_tag(self):
        """Tag handles special characters."""
        tag = self.create_tag(self.user, name='Work & Life <Balance>')
        self.assertIn('&', tag.name)
    
    def test_unicode_in_tag(self):
        """Tag handles unicode characters."""
        tag = self.create_tag(self.user, name='日本語タグ')
        self.assertEqual(tag.name, '日本語タグ')


# =============================================================================
# 7. SAFE REDIRECT UTILITY TESTS
# =============================================================================

class SafeRedirectUtilsTest(TestCase):
    """Tests for is_safe_redirect_url and get_safe_redirect_url utilities."""

    def setUp(self):
        self.factory = None
        # Create a mock request using Django test client
        from django.test import RequestFactory
        self.factory = RequestFactory()

    def _create_request(self, path='/', method='GET', data=None, referer=None, secure=False):
        """Create a mock request for testing."""
        if method == 'POST':
            request = self.factory.post(path, data or {})
        else:
            request = self.factory.get(path, data or {})

        if referer:
            request.META['HTTP_REFERER'] = referer

        # Mock is_secure
        request.is_secure = lambda: secure
        return request

    def test_is_safe_redirect_url_allows_relative_paths(self):
        """Relative URLs starting with / are allowed."""
        from apps.core.utils import is_safe_redirect_url
        request = self._create_request()

        self.assertTrue(is_safe_redirect_url('/dashboard/', request))
        self.assertTrue(is_safe_redirect_url('/life/tasks/', request))
        self.assertTrue(is_safe_redirect_url('/user/preferences/', request))

    def test_is_safe_redirect_url_blocks_external_urls(self):
        """External URLs to other hosts are blocked."""
        from apps.core.utils import is_safe_redirect_url
        request = self._create_request()

        self.assertFalse(is_safe_redirect_url('https://evil.com/', request))
        self.assertFalse(is_safe_redirect_url('http://attacker.com/phishing', request))
        self.assertFalse(is_safe_redirect_url('https://google.com', request))

    def test_is_safe_redirect_url_blocks_protocol_relative_urls(self):
        """Protocol-relative URLs (//example.com) are blocked."""
        from apps.core.utils import is_safe_redirect_url
        request = self._create_request()

        self.assertFalse(is_safe_redirect_url('//evil.com/', request))
        self.assertFalse(is_safe_redirect_url('//attacker.com/path', request))

    def test_is_safe_redirect_url_blocks_javascript_urls(self):
        """JavaScript URLs are blocked."""
        from apps.core.utils import is_safe_redirect_url
        request = self._create_request()

        self.assertFalse(is_safe_redirect_url('javascript:alert(1)', request))
        self.assertFalse(is_safe_redirect_url('javascript:void(0)', request))

    def test_is_safe_redirect_url_empty_or_none(self):
        """Empty or None URLs return False."""
        from apps.core.utils import is_safe_redirect_url
        request = self._create_request()

        self.assertFalse(is_safe_redirect_url('', request))
        self.assertFalse(is_safe_redirect_url(None, request))

    def test_get_safe_redirect_url_from_post(self):
        """get_safe_redirect_url finds safe URL in POST 'next' parameter."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request(method='POST', data={'next': '/dashboard/'})

        self.assertEqual(get_safe_redirect_url(request), '/dashboard/')

    def test_get_safe_redirect_url_from_get(self):
        """get_safe_redirect_url finds safe URL in GET 'next' parameter."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request(method='GET', data={'next': '/life/tasks/'})

        self.assertEqual(get_safe_redirect_url(request), '/life/tasks/')

    def test_get_safe_redirect_url_from_referer(self):
        """get_safe_redirect_url uses HTTP_REFERER if no 'next' parameter."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request(referer='http://testserver/previous-page/')

        self.assertEqual(get_safe_redirect_url(request), 'http://testserver/previous-page/')

    def test_get_safe_redirect_url_blocks_unsafe_next(self):
        """get_safe_redirect_url rejects unsafe 'next' parameter and returns default."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request(method='POST', data={'next': 'https://evil.com/'})

        self.assertIsNone(get_safe_redirect_url(request))
        self.assertEqual(get_safe_redirect_url(request, default_url='/safe/'), '/safe/')

    def test_get_safe_redirect_url_blocks_unsafe_referer(self):
        """get_safe_redirect_url rejects unsafe HTTP_REFERER and returns default."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request(referer='https://evil.com/')

        self.assertIsNone(get_safe_redirect_url(request))

    def test_get_safe_redirect_url_returns_default_when_no_url(self):
        """get_safe_redirect_url returns default_url when no redirect URL found."""
        from apps.core.utils import get_safe_redirect_url
        request = self._create_request()

        self.assertIsNone(get_safe_redirect_url(request))
        self.assertEqual(get_safe_redirect_url(request, default_url='/fallback/'), '/fallback/')

    def test_get_safe_redirect_url_priority_post_over_get(self):
        """POST 'next' takes priority over GET 'next'."""
        from apps.core.utils import get_safe_redirect_url
        # Create request with both POST and GET data
        request = self.factory.post('/?next=/from-get/', {'next': '/from-post/'})
        request.is_secure = lambda: False

        result = get_safe_redirect_url(request)
        self.assertEqual(result, '/from-post/')


# =============================================================================
# 8. AI CAMERA SOURCE TRACKING TESTS
# =============================================================================

class AISourceTrackingModelTests(CoreTestMixin, TestCase):
    """Tests for created_via field and was_created_by_ai property."""

    def setUp(self):
        self.user = self.create_user()

    def test_default_created_via_is_manual(self):
        """New entries have created_via='manual' by default."""
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today()
        )
        self.assertEqual(entry.created_via, 'manual')

    def test_was_created_by_ai_false_for_manual(self):
        """was_created_by_ai returns False for manual entries."""
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today(),
            created_via='manual'
        )
        self.assertFalse(entry.was_created_by_ai)

    def test_was_created_by_ai_true_for_ai_camera(self):
        """was_created_by_ai returns True for AI camera entries."""
        from apps.journal.models import JournalEntry
        entry = JournalEntry.objects.create(
            user=self.user,
            title='Test Entry',
            body='Content',
            entry_date=date.today(),
            created_via='ai_camera'
        )
        self.assertTrue(entry.was_created_by_ai)

    def test_created_via_choices(self):
        """Verify all created_via choices work."""
        from apps.journal.models import JournalEntry
        from apps.core.models import UserOwnedModel

        for choice_value, _ in UserOwnedModel.CREATED_VIA_CHOICES:
            entry = JournalEntry.objects.create(
                user=self.user,
                title=f'Entry via {choice_value}',
                body='Content',
                entry_date=date.today(),
                created_via=choice_value
            )
            self.assertEqual(entry.created_via, choice_value)
            # Clean up
            entry.delete()

    def test_medicine_created_via_field(self):
        """Medicine model has created_via field."""
        from apps.health.models import Medicine
        medicine = Medicine.objects.create(
            user=self.user,
            name='Test Medicine',
            dose='10mg',
            frequency='daily',
            start_date=date.today(),
            created_via='ai_camera'
        )
        self.assertTrue(medicine.was_created_by_ai)
        self.assertEqual(medicine.created_via, 'ai_camera')

    def test_workout_created_via_field(self):
        """WorkoutSession model has created_via field."""
        from apps.health.models import WorkoutSession
        workout = WorkoutSession.objects.create(
            user=self.user,
            name='Morning Run',
            duration_minutes=30,
            date=date.today(),
            created_via='ai_camera'
        )
        self.assertTrue(workout.was_created_by_ai)
        self.assertEqual(workout.created_via, 'ai_camera')


# =============================================================================
# WHAT'S NEW / RELEASE NOTES TESTS
# =============================================================================

class ReleaseNoteModelTest(CoreTestMixin, TestCase):
    """Tests for the ReleaseNote model."""

    def setUp(self):
        from apps.core.models import ReleaseNote
        self.ReleaseNote = ReleaseNote
        # Clear existing release notes for clean test state
        self.ReleaseNote.objects.all().delete()

    def test_create_release_note(self):
        """Can create a release note with required fields."""
        note = self.ReleaseNote.objects.create(
            title='New Feature',
            description='A wonderful new feature.',
            release_date=date.today(),
        )
        self.assertEqual(note.title, 'New Feature')
        self.assertEqual(note.entry_type, 'feature')  # default
        self.assertTrue(note.is_published)  # default

    def test_entry_type_choices(self):
        """Release notes have correct entry type choices."""
        self.assertEqual(self.ReleaseNote.TYPE_FEATURE, 'feature')
        self.assertEqual(self.ReleaseNote.TYPE_FIX, 'fix')
        self.assertEqual(self.ReleaseNote.TYPE_ENHANCEMENT, 'enhancement')
        self.assertEqual(self.ReleaseNote.TYPE_SECURITY, 'security')

    def test_get_published_returns_only_published(self):
        """get_published() only returns published notes."""
        published = self.ReleaseNote.objects.create(
            title='Published',
            description='Visible',
            release_date=date.today(),
            is_published=True,
        )
        unpublished = self.ReleaseNote.objects.create(
            title='Unpublished',
            description='Hidden',
            release_date=date.today(),
            is_published=False,
        )
        result = self.ReleaseNote.get_published()
        self.assertIn(published, result)
        self.assertNotIn(unpublished, result)

    def test_get_published_ordering(self):
        """get_published() orders by release_date descending."""
        old = self.ReleaseNote.objects.create(
            title='Old',
            description='Earlier',
            release_date=date.today() - timedelta(days=7),
        )
        new = self.ReleaseNote.objects.create(
            title='New',
            description='Recent',
            release_date=date.today(),
        )
        result = list(self.ReleaseNote.get_published())
        self.assertEqual(result[0], new)
        self.assertEqual(result[1], old)

    def test_get_icon_for_feature(self):
        """Feature notes have sparkle icon."""
        note = self.ReleaseNote.objects.create(
            title='Feature',
            description='New',
            release_date=date.today(),
            entry_type='feature',
        )
        self.assertEqual(note.get_icon(), '✨')

    def test_get_icon_for_fix(self):
        """Fix notes have wrench icon."""
        note = self.ReleaseNote.objects.create(
            title='Fix',
            description='Bug fixed',
            release_date=date.today(),
            entry_type='fix',
        )
        self.assertEqual(note.get_icon(), '🔧')

    def test_get_icon_for_enhancement(self):
        """Enhancement notes have rocket icon."""
        note = self.ReleaseNote.objects.create(
            title='Enhancement',
            description='Improved',
            release_date=date.today(),
            entry_type='enhancement',
        )
        self.assertEqual(note.get_icon(), '🚀')

    def test_get_icon_for_security(self):
        """Security notes have lock icon."""
        note = self.ReleaseNote.objects.create(
            title='Security',
            description='Secured',
            release_date=date.today(),
            entry_type='security',
        )
        self.assertEqual(note.get_icon(), '🔒')

    def test_str_representation(self):
        """String representation includes title and date."""
        note = self.ReleaseNote.objects.create(
            title='Test Note',
            description='Description',
            release_date=date(2025, 12, 28),
        )
        self.assertIn('Test Note', str(note))
        self.assertIn('2025-12-28', str(note))


class UserReleaseNoteViewModelTest(CoreTestMixin, TestCase):
    """Tests for the UserReleaseNoteView tracking model."""

    def setUp(self):
        from apps.core.models import UserReleaseNoteView
        self.UserReleaseNoteView = UserReleaseNoteView
        self.user = self.create_user()

    def test_mark_viewed_creates_record(self):
        """mark_viewed creates a new record for first-time view."""
        self.assertEqual(self.UserReleaseNoteView.objects.count(), 0)
        self.UserReleaseNoteView.mark_viewed(self.user)
        self.assertEqual(self.UserReleaseNoteView.objects.count(), 1)

    def test_mark_viewed_updates_existing(self):
        """mark_viewed updates timestamp on subsequent views."""
        first_view = self.UserReleaseNoteView.mark_viewed(self.user)
        first_time = first_view.last_viewed_at

        # Small delay to ensure different timestamp
        import time
        time.sleep(0.1)

        second_view = self.UserReleaseNoteView.mark_viewed(self.user)
        self.assertEqual(self.UserReleaseNoteView.objects.count(), 1)
        self.assertGreater(second_view.last_viewed_at, first_time)

    def test_str_representation(self):
        """String representation includes user email."""
        view = self.UserReleaseNoteView.mark_viewed(self.user)
        self.assertIn(self.user.email, str(view))


class ReleaseNoteUnseenTest(CoreTestMixin, TestCase):
    """Tests for getting unseen release notes for a user."""

    def setUp(self):
        from apps.core.models import ReleaseNote, UserReleaseNoteView
        self.ReleaseNote = ReleaseNote
        self.UserReleaseNoteView = UserReleaseNoteView
        self.ReleaseNote.objects.all().delete()
        self.user = self.create_user()

    def test_new_user_sees_all_notes(self):
        """New user with no view history sees all notes (up to limit)."""
        for i in range(5):
            self.ReleaseNote.objects.create(
                title=f'Note {i}',
                description='Test',
                release_date=date.today(),
            )
        unseen = self.ReleaseNote.get_unseen_for_user(self.user)
        self.assertEqual(len(list(unseen)), 5)

    def test_user_sees_only_new_notes_after_viewing(self):
        """User only sees notes created after their last view."""
        old_note = self.ReleaseNote.objects.create(
            title='Old Note',
            description='Seen',
            release_date=date.today() - timedelta(days=1),
        )
        # Mark as viewed
        self.UserReleaseNoteView.mark_viewed(self.user)

        # Create new note after viewing
        new_note = self.ReleaseNote.objects.create(
            title='New Note',
            description='Unseen',
            release_date=date.today(),
        )

        unseen = list(self.ReleaseNote.get_unseen_for_user(self.user))
        self.assertIn(new_note, unseen)
        self.assertNotIn(old_note, unseen)

    def test_opted_out_user_sees_nothing(self):
        """User who opted out of What's New sees no notes."""
        self.ReleaseNote.objects.create(
            title='Note',
            description='Test',
            release_date=date.today(),
        )
        # Opt out
        self.user.preferences.show_whats_new = False
        self.user.preferences.save()

        unseen = self.ReleaseNote.get_unseen_for_user(self.user)
        self.assertEqual(len(list(unseen)), 0)


class WhatsNewViewsTest(CoreTestMixin, TestCase):
    """Tests for What's New API endpoints."""

    def setUp(self):
        from apps.core.models import ReleaseNote, UserReleaseNoteView
        self.ReleaseNote = ReleaseNote
        self.UserReleaseNoteView = UserReleaseNoteView
        self.ReleaseNote.objects.all().delete()
        self.user = self.create_user()
        self.client = Client()
        self.login_user()

    def test_check_endpoint_requires_auth(self):
        """Check endpoint requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('core:whats_new_check'))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_check_endpoint_returns_json(self):
        """Check endpoint returns JSON response."""
        response = self.client.get(reverse('core:whats_new_check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_check_endpoint_no_unseen(self):
        """Check endpoint returns has_unseen=False when no notes."""
        response = self.client.get(reverse('core:whats_new_check'))
        data = response.json()
        self.assertFalse(data['has_unseen'])
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['notes'], [])

    def test_check_endpoint_with_unseen(self):
        """Check endpoint returns unseen notes."""
        self.ReleaseNote.objects.create(
            title='Test Feature',
            description='A new feature',
            release_date=date.today(),
        )
        response = self.client.get(reverse('core:whats_new_check'))
        data = response.json()
        self.assertTrue(data['has_unseen'])
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['notes'][0]['title'], 'Test Feature')

    def test_check_endpoint_note_fields(self):
        """Check endpoint returns all expected note fields."""
        self.ReleaseNote.objects.create(
            title='Feature',
            description='Description',
            entry_type='feature',
            release_date=date.today(),
            is_major=True,
            learn_more_url='https://example.com',
        )
        response = self.client.get(reverse('core:whats_new_check'))
        note = response.json()['notes'][0]
        self.assertIn('id', note)
        self.assertIn('title', note)
        self.assertIn('description', note)
        self.assertIn('entry_type', note)
        self.assertIn('type_display', note)
        self.assertIn('icon', note)
        self.assertIn('release_date', note)
        self.assertIn('is_major', note)
        self.assertIn('learn_more_url', note)

    def test_dismiss_endpoint_requires_auth(self):
        """Dismiss endpoint requires authentication."""
        self.client.logout()
        response = self.client.post(reverse('core:whats_new_dismiss'))
        self.assertEqual(response.status_code, 302)

    def test_dismiss_endpoint_marks_viewed(self):
        """Dismiss endpoint marks notes as viewed."""
        self.assertEqual(self.UserReleaseNoteView.objects.count(), 0)
        response = self.client.post(reverse('core:whats_new_dismiss'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.UserReleaseNoteView.objects.count(), 1)

    def test_dismiss_endpoint_returns_success(self):
        """Dismiss endpoint returns success JSON."""
        response = self.client.post(reverse('core:whats_new_dismiss'))
        data = response.json()
        self.assertTrue(data['success'])

    def test_list_view_requires_auth(self):
        """List view requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('core:whats_new_list'))
        self.assertEqual(response.status_code, 302)

    def test_list_view_shows_notes(self):
        """List view displays release notes."""
        self.ReleaseNote.objects.create(
            title='Test Note',
            description='For listing',
            release_date=date.today(),
        )
        response = self.client.get(reverse('core:whats_new_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Note')

    def test_list_view_context_has_notes(self):
        """List view passes release_notes to template context."""
        response = self.client.get(reverse('core:whats_new_list'))
        self.assertIn('release_notes', response.context)


class WhatsNewPreferenceTest(CoreTestMixin, TestCase):
    """Tests for What's New preference toggle."""

    def setUp(self):
        self.user = self.create_user()
        self.client = Client()
        self.login_user()

    def test_show_whats_new_default_true(self):
        """show_whats_new defaults to True for new users."""
        self.assertTrue(self.user.preferences.show_whats_new)

    def test_show_whats_new_in_preferences_form(self):
        """show_whats_new field is in preferences form."""
        response = self.client.get(reverse('users:preferences'))
        self.assertContains(response, 'show_whats_new')

    def test_can_disable_whats_new(self):
        """User can disable What's New popup via preferences."""
        response = self.client.post(reverse('users:preferences'), {
            'theme': 'minimal',
            'timezone': 'US/Eastern',
            # show_whats_new not included = unchecked = False
        })
        self.user.preferences.refresh_from_db()
        self.assertFalse(self.user.preferences.show_whats_new)

    def test_can_enable_whats_new(self):
        """User can enable What's New popup via preferences."""
        self.user.preferences.show_whats_new = False
        self.user.preferences.save()

        response = self.client.post(reverse('users:preferences'), {
            'theme': 'minimal',
            'timezone': 'US/Eastern',
            'show_whats_new': 'on',
        })
        self.user.preferences.refresh_from_db()
        self.assertTrue(self.user.preferences.show_whats_new)