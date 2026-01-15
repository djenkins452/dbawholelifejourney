"""
User Signals Tests

Tests for signal handlers that create related objects automatically.

Location: apps/users/tests/test_signals.py
"""

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.health.models import CycleSettings

User = get_user_model()


class CycleTrackingSignalTest(TestCase):
    """Tests for auto-enable cycle tracking signal."""

    def test_female_gender_creates_cycle_settings(self):
        """Setting gender to female auto-creates CycleSettings with tracking enabled."""
        user = User.objects.create_user(
            email="female@example.com", password="testpass123"
        )
        prefs = user.preferences
        prefs.gender = "female"
        prefs.save()

        # CycleSettings should be auto-created
        self.assertTrue(CycleSettings.objects.filter(user=user).exists())
        settings = CycleSettings.objects.get(user=user)
        self.assertTrue(settings.cycle_tracking_enabled)

    def test_male_gender_does_not_create_cycle_settings(self):
        """Setting gender to male does NOT create CycleSettings."""
        user = User.objects.create_user(
            email="male@example.com", password="testpass123"
        )
        prefs = user.preferences
        prefs.gender = "male"
        prefs.save()

        # CycleSettings should NOT be created
        self.assertFalse(CycleSettings.objects.filter(user=user).exists())

    def test_prefer_not_to_say_does_not_create_cycle_settings(self):
        """Setting gender to prefer_not_to_say does NOT create CycleSettings."""
        user = User.objects.create_user(
            email="pnts@example.com", password="testpass123"
        )
        prefs = user.preferences
        prefs.gender = "prefer_not_to_say"
        prefs.save()

        # CycleSettings should NOT be created
        self.assertFalse(CycleSettings.objects.filter(user=user).exists())

    def test_existing_cycle_settings_not_overwritten(self):
        """If CycleSettings already exists, it is not overwritten."""
        user = User.objects.create_user(
            email="existing@example.com", password="testpass123"
        )

        # Create CycleSettings with tracking disabled
        CycleSettings.objects.create(user=user, cycle_tracking_enabled=False)

        # Now set gender to female
        prefs = user.preferences
        prefs.gender = "female"
        prefs.save()

        # CycleSettings should still have tracking disabled (not overwritten)
        settings = CycleSettings.objects.get(user=user)
        self.assertFalse(settings.cycle_tracking_enabled)

    def test_changing_from_female_does_not_delete_settings(self):
        """Changing gender from female does NOT delete CycleSettings."""
        user = User.objects.create_user(
            email="change@example.com", password="testpass123"
        )
        prefs = user.preferences

        # Set to female first
        prefs.gender = "female"
        prefs.save()
        self.assertTrue(CycleSettings.objects.filter(user=user).exists())

        # Now change to male
        prefs.gender = "male"
        prefs.save()

        # CycleSettings should still exist
        self.assertTrue(CycleSettings.objects.filter(user=user).exists())
