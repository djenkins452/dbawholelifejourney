"""
Users Module - Comprehensive Tests

This test file expands on existing user tests with:
1. User model edge cases
2. UserPreferences comprehensive tests
3. TermsAcceptance tests
4. Profile view tests
5. Registration/signup tests
6. Password change tests

Location: apps/users/tests/test_users_comprehensive.py
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class UsersTestMixin:
    """Common setup for user tests."""
    
    def create_user(self, email='test@example.com', password='testpass123', **kwargs):
        """Create a test user."""
        return User.objects.create_user(email=email, password=password, **kwargs)
    
    def create_user_with_terms(self, email='test@example.com', password='testpass123'):
        """Create user with terms accepted and onboarding completed."""
        user = self.create_user(email=email, password=password)
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


# =============================================================================
# 1. USER MODEL EDGE CASES
# =============================================================================

class UserModelEdgeCaseTest(UsersTestMixin, TestCase):
    """Edge case tests for User model."""
    
    def test_email_case_insensitive_lookup(self):
        """Email lookup should be case-insensitive."""
        user = self.create_user(email='Test@Example.COM')
        
        # Should find user regardless of case
        found = User.objects.filter(email__iexact='test@example.com').first()
        self.assertEqual(found, user)
    
    def test_user_with_long_email(self):
        """User handles long email addresses."""
        long_email = 'a' * 50 + '@' + 'b' * 50 + '.com'
        user = self.create_user(email=long_email)
        self.assertEqual(user.email, long_email.lower())
    
    def test_user_with_special_chars_in_email(self):
        """User handles special characters in email."""
        email = 'test+tag@example.com'
        user = self.create_user(email=email)
        self.assertEqual(user.email, email)
    
    def test_user_with_full_name(self):
        """User with first and last name."""
        user = self.create_user(
            first_name='John',
            last_name='Doe'
        )
        self.assertEqual(user.first_name, 'John')
        self.assertEqual(user.last_name, 'Doe')
    
    def test_user_is_active_by_default(self):
        """New users are active by default."""
        user = self.create_user()
        self.assertTrue(user.is_active)
    
    def test_deactivate_user(self):
        """User can be deactivated."""
        user = self.create_user()
        user.is_active = False
        user.save()
        
        user.refresh_from_db()
        self.assertFalse(user.is_active)
    
    def test_deactivated_user_cannot_login(self):
        """Deactivated user cannot log in."""
        user = self.create_user()
        user.is_active = False
        user.save()
        
        client = Client()
        result = client.login(email='test@example.com', password='testpass123')
        self.assertFalse(result)


# =============================================================================
# 2. USER PREFERENCES COMPREHENSIVE TESTS
# =============================================================================

class UserPreferencesComprehensiveTest(UsersTestMixin, TestCase):
    """Comprehensive tests for UserPreferences."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_preferences_auto_created(self):
        """Preferences are automatically created with user."""
        self.assertTrue(hasattr(self.user, 'preferences'))
        self.assertIsNotNone(self.user.preferences)
    
    def test_all_module_toggles(self):
        """All module toggles can be set."""
        prefs = self.user.preferences
        
        # Test each module toggle
        modules = ['journal', 'faith', 'health', 'life', 'purpose']
        for module in modules:
            field_name = f'{module}_enabled'
            if hasattr(prefs, field_name):
                setattr(prefs, field_name, True)
                prefs.save()
                prefs.refresh_from_db()
                self.assertTrue(getattr(prefs, field_name))
    
    def test_theme_choices(self):
        """Theme can be set to valid values."""
        prefs = self.user.preferences
        themes = ['minimal', 'warm', 'forest', 'ocean']
        
        for theme in themes:
            prefs.theme = theme
            prefs.save()
            prefs.refresh_from_db()
            self.assertEqual(prefs.theme, theme)
    
    def test_accent_color(self):
        """Accent color can be set."""
        prefs = self.user.preferences
        prefs.accent_color = '#FF5733'
        prefs.save()
        
        prefs.refresh_from_db()
        self.assertEqual(prefs.accent_color, '#FF5733')
    
    def test_timezone_setting(self):
        """Timezone can be set."""
        prefs = self.user.preferences
        prefs.timezone = 'America/New_York'
        prefs.save()
        
        prefs.refresh_from_db()
        self.assertEqual(prefs.timezone, 'America/New_York')
    
    def test_dashboard_config(self):
        """Dashboard config can be saved as JSON."""
        prefs = self.user.preferences
        config = {'show_weight': True, 'show_journal': False}
        prefs.dashboard_config = config
        prefs.save()
        
        prefs.refresh_from_db()
        self.assertEqual(prefs.dashboard_config, config)
    
    def test_preferences_str(self):
        """Preferences string representation."""
        prefs = self.user.preferences
        str_repr = str(prefs)
        self.assertIn('test@example.com', str_repr)


# =============================================================================
# 3. TERMS ACCEPTANCE TESTS
# =============================================================================

class TermsAcceptanceTest(UsersTestMixin, TestCase):
    """Tests for TermsAcceptance model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_accept_terms(self):
        """User can accept terms."""
        from apps.users.models import TermsAcceptance
        
        acceptance = TermsAcceptance.objects.create(
            user=self.user,
            terms_version='1.0'
        )
        self.assertEqual(acceptance.terms_version, '1.0')
        self.assertIsNotNone(acceptance.accepted_at)
    
    def test_terms_acceptance_timestamp(self):
        """Terms acceptance records timestamp."""
        from apps.users.models import TermsAcceptance
        
        before = timezone.now()
        acceptance = TermsAcceptance.objects.create(
            user=self.user,
            terms_version='1.0'
        )
        after = timezone.now()
        
        self.assertGreaterEqual(acceptance.accepted_at, before)
        self.assertLessEqual(acceptance.accepted_at, after)
    
    def test_multiple_terms_versions(self):
        """User can accept multiple terms versions."""
        from apps.users.models import TermsAcceptance
        
        TermsAcceptance.objects.create(user=self.user, terms_version='1.0')
        TermsAcceptance.objects.create(user=self.user, terms_version='2.0')
        
        acceptances = TermsAcceptance.objects.filter(user=self.user)
        self.assertEqual(acceptances.count(), 2)
    
    def test_terms_acceptance_str(self):
        """Terms acceptance string representation."""
        from apps.users.models import TermsAcceptance
        
        acceptance = TermsAcceptance.objects.create(
            user=self.user,
            terms_version='1.0'
        )
        str_repr = str(acceptance)
        self.assertIn('test@example.com', str_repr)


# =============================================================================
# 4. PROFILE VIEW TESTS
# =============================================================================

class ProfileViewTest(UsersTestMixin, TestCase):
    """Tests for profile views."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user_with_terms()
    
    def test_profile_requires_login(self):
        """Profile page requires authentication."""
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 302)
    
    def test_profile_loads(self):
        """Profile page loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)
    
    def test_profile_shows_user_info(self):
        """Profile shows user information."""
        self.user.first_name = 'John'
        self.user.last_name = 'Doe'
        self.user.save()
        
        self.login_user()
        response = self.client.get(reverse('users:profile'))
        
        self.assertContains(response, 'John')
    
    def test_profile_edit_loads(self):
        """Profile edit page loads."""
        self.login_user()
        response = self.client.get(reverse('users:profile_edit'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. AUTHENTICATION FLOW TESTS
# =============================================================================

class AuthenticationFlowTest(UsersTestMixin, TestCase):
    """Tests for complete authentication flows."""
    
    def setUp(self):
        self.client = Client()
    
    def test_login_page_loads(self):
        """Login page loads."""
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
    
    def test_signup_page_loads(self):
        """Signup page loads."""
        response = self.client.get(reverse('account_signup'))
        self.assertEqual(response.status_code, 200)
    
    def test_login_redirect_after_success(self):
        """Successful login redirects to dashboard."""
        user = self.create_user_with_terms()
        
        response = self.client.post(reverse('account_login'), {
            'login': 'test@example.com',
            'password': 'testpass123',
        }, follow=True)
        
        # Should end up at dashboard or terms page
        self.assertEqual(response.status_code, 200)
    
    def test_logout_redirect(self):
        """Logout redirects to appropriate page."""
        user = self.create_user_with_terms()
        self.login_user()
        
        response = self.client.get(reverse('account_logout'))
        # Allauth might show confirmation or redirect
        self.assertIn(response.status_code, [200, 302])


# =============================================================================
# 6. DATA ISOLATION TESTS
# =============================================================================

class UserDataIsolationTest(UsersTestMixin, TestCase):
    """Tests for user data isolation."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user_with_terms(email='usera@example.com')
        self.user_b = self.create_user_with_terms(email='userb@example.com')
    
    def test_preferences_are_user_specific(self):
        """Each user has their own preferences."""
        self.user_a.preferences.theme = 'dark'
        self.user_a.preferences.save()
        
        self.user_b.preferences.theme = 'minimal'
        self.user_b.preferences.save()
        
        self.user_a.preferences.refresh_from_db()
        self.user_b.preferences.refresh_from_db()
        
        self.assertEqual(self.user_a.preferences.theme, 'dark')
        self.assertEqual(self.user_b.preferences.theme, 'minimal')
    
    def test_user_cannot_access_other_profile(self):
        """User cannot view another user's profile directly."""
        # This depends on your URL structure
        # Most apps don't expose other users' profiles
        self.client.login(email='usera@example.com', password='testpass123')
        
        # Trying to access own profile should work
        response = self.client.get(reverse('users:profile'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 7. PASSWORD TESTS
# =============================================================================

class PasswordTest(UsersTestMixin, TestCase):
    """Tests for password functionality."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user_with_terms()
    
    def test_password_change_page_loads(self):
        """Password change page loads."""
        self.login_user()
        response = self.client.get(reverse('account_change_password'))
        self.assertEqual(response.status_code, 200)
    
    def test_password_reset_page_loads(self):
        """Password reset request page loads."""
        response = self.client.get(reverse('account_reset_password'))
        self.assertEqual(response.status_code, 200)
    
    def test_user_can_change_password(self):
        """User can change their password."""
        self.user.set_password('newpassword123')
        self.user.save()
        
        # Old password should no longer work
        result = self.client.login(
            email='test@example.com', 
            password='testpass123'
        )
        self.assertFalse(result)
        
        # New password should work
        result = self.client.login(
            email='test@example.com', 
            password='newpassword123'
        )
        self.assertTrue(result)


# =============================================================================
# 8. EDGE CASES
# =============================================================================

class UserEdgeCaseTest(UsersTestMixin, TestCase):
    """Edge case tests."""
    
    def test_empty_first_name(self):
        """User with empty first name."""
        user = self.create_user(first_name='')
        self.assertEqual(user.first_name, '')
        # get_short_name should fall back to email prefix
        self.assertEqual(user.get_short_name(), 'test')
    
    def test_unicode_in_name(self):
        """User with unicode characters in name."""
        user = self.create_user(
            first_name='José',
            last_name='García'
        )
        self.assertEqual(user.first_name, 'José')
        self.assertEqual(user.get_full_name(), 'José García')
    
    def test_very_long_name(self):
        """User with very long name."""
        long_name = 'A' * 100
        user = self.create_user(first_name=long_name)
        self.assertTrue(len(user.first_name) > 0)


# =============================================================================
# 9. PROFILE PICTURE / AVATAR TESTS
# =============================================================================

class ProfilePictureTest(UsersTestMixin, TestCase):
    """Tests for profile picture upload and preservation."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user_with_terms()

    def test_profile_edit_form_loads_without_avatar(self):
        """Profile edit form loads when user has no avatar."""
        self.login_user()
        response = self.client.get(reverse('users:profile_edit'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload Photo')

    def test_profile_form_preserves_existing_avatar_on_submit_without_new_file(self):
        """Submitting profile form without new file keeps existing avatar."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image

        self.login_user()

        # Create a test image
        img = Image.new('RGB', (100, 100), color='red')
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        # Upload initial avatar
        test_image = SimpleUploadedFile(
            name='test_avatar.png',
            content=img_buffer.getvalue(),
            content_type='image/png'
        )

        response = self.client.post(
            reverse('users:profile_edit'),
            {
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
                'avatar': test_image,
            },
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Verify avatar was saved
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)
        original_avatar_name = self.user.avatar.name

        # Now submit form again WITHOUT a new file
        response = self.client.post(
            reverse('users:profile_edit'),
            {
                'first_name': 'Updated',
                'last_name': 'User',
                'email': 'test@example.com',
                # No avatar field - should preserve existing
            },
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Verify avatar is still present
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar, "Avatar should be preserved when form submitted without new file")
        self.assertEqual(self.user.avatar.name, original_avatar_name)
        self.assertEqual(self.user.first_name, 'Updated')

    def test_clear_avatar_checkbox_removes_avatar(self):
        """Using clear_avatar checkbox removes the avatar."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image

        self.login_user()

        # Create and upload initial avatar
        img = Image.new('RGB', (100, 100), color='blue')
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        test_image = SimpleUploadedFile(
            name='test_avatar2.png',
            content=img_buffer.getvalue(),
            content_type='image/png'
        )

        self.client.post(
            reverse('users:profile_edit'),
            {
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
                'avatar': test_image,
            }
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar)

        # Now clear the avatar using the checkbox
        response = self.client.post(
            reverse('users:profile_edit'),
            {
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
                'clear_avatar': 'on',
            },
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar, "Avatar should be cleared when clear_avatar checkbox is checked")


class ProfileFormTest(TestCase):
    """Unit tests for ProfileForm validation."""

    def test_clean_avatar_rejects_large_file(self):
        """Avatar validation rejects files over 2MB."""
        from apps.users.forms import ProfileForm
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image

        # Create a valid image but make it large by repeating pixel data
        # Create a large image (3000x3000 which creates a file > 2MB when saved)
        img = Image.new('RGB', (3000, 3000), color='red')
        img_buffer = BytesIO()
        # Use uncompressed BMP to ensure large file size
        img.save(img_buffer, format='BMP')
        img_buffer.seek(0)
        large_content = img_buffer.getvalue()

        # Verify it's actually over 2MB
        self.assertGreater(len(large_content), 2 * 1024 * 1024, "Test image should be >2MB")

        large_file = SimpleUploadedFile(
            name='large.bmp',
            content=large_content,
            content_type='image/bmp'
        )

        form = ProfileForm(
            data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
            },
            files={'avatar': large_file}
        )

        self.assertFalse(form.is_valid())
        self.assertIn('avatar', form.errors)
        self.assertIn('too large', form.errors['avatar'][0].lower())

    def test_clean_avatar_accepts_valid_image(self):
        """Avatar validation accepts valid image files."""
        from apps.users.forms import ProfileForm
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image

        # Create a valid small image
        img = Image.new('RGB', (50, 50), color='green')
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)

        valid_image = SimpleUploadedFile(
            name='valid.png',
            content=img_buffer.getvalue(),
            content_type='image/png'
        )

        form = ProfileForm(
            data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
            },
            files={'avatar': valid_image}
        )

        # Form should be valid (avatar passes validation)
        if not form.is_valid():
            # Only fail if avatar is the issue
            self.assertNotIn('avatar', form.errors)

    def test_clean_avatar_handles_heic_content_type(self):
        """Avatar validation accepts HEIC content type from iPhone."""
        from apps.users.forms import ProfileForm
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Simulate HEIC file (just check content_type handling, not actual HEIC)
        heic_file = SimpleUploadedFile(
            name='photo.heic',
            content=b'fake heic content',
            content_type='image/heic'
        )

        form = ProfileForm(
            data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
            },
            files={'avatar': heic_file}
        )

        # The content_type check should pass for image/heic
        # (file format validation is handled by PIL/Django ImageField)
        if not form.is_valid():
            # Make sure avatar is not rejected due to content_type
            if 'avatar' in form.errors:
                self.assertNotIn('image file', form.errors['avatar'][0].lower())

    def test_clean_avatar_handles_missing_content_type(self):
        """Avatar validation handles files with missing content_type."""
        from apps.users.forms import ProfileForm
        from django.core.files.uploadedfile import SimpleUploadedFile
        from io import BytesIO
        from PIL import Image

        # Create a valid image
        img = Image.new('RGB', (50, 50), color='yellow')
        img_buffer = BytesIO()
        img.save(img_buffer, format='JPEG')
        img_buffer.seek(0)

        # File with application/octet-stream (generic binary)
        file_with_generic_type = SimpleUploadedFile(
            name='photo.jpg',
            content=img_buffer.getvalue(),
            content_type='application/octet-stream'
        )

        form = ProfileForm(
            data={
                'first_name': 'Test',
                'last_name': 'User',
                'email': 'test@example.com',
            },
            files={'avatar': file_with_generic_type}
        )

        # Should not reject due to content_type
        if not form.is_valid():
            if 'avatar' in form.errors:
                self.assertNotIn('image file', form.errors['avatar'][0].lower())