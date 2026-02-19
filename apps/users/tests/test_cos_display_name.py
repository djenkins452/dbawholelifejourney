from django.test import TestCase

from apps.users.models import User, UserPreferences


class CosDisplayNameTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123', first_name='Test'
        )
        self.prefs = self.user.preferences

    def test_default_cos_display_name_is_empty(self):
        self.assertEqual(self.prefs.cos_display_name, '')

    def test_get_cos_name_returns_default_when_empty(self):
        self.assertEqual(self.prefs.get_cos_name(), 'Chief of Staff')

    def test_get_cos_name_returns_custom_name(self):
        self.prefs.cos_display_name = 'Max'
        self.prefs.save()
        self.assertEqual(self.prefs.get_cos_name(), 'Max')

    def test_get_cos_name_strips_whitespace(self):
        self.prefs.cos_display_name = '  Max  '
        self.prefs.save()
        self.assertEqual(self.prefs.get_cos_name(), 'Max')

    def test_get_cos_name_returns_default_for_whitespace_only(self):
        self.prefs.cos_display_name = '   '
        self.prefs.save()
        self.assertEqual(self.prefs.get_cos_name(), 'Chief of Staff')

    def test_cos_display_name_max_length(self):
        field = UserPreferences._meta.get_field('cos_display_name')
        self.assertEqual(field.max_length, 50)

    def test_cos_display_name_save_and_retrieve(self):
        self.prefs.cos_display_name = 'Jarvis'
        self.prefs.save()
        refreshed = UserPreferences.objects.get(pk=self.prefs.pk)
        self.assertEqual(refreshed.cos_display_name, 'Jarvis')
