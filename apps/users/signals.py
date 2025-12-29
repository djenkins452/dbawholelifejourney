"""
Whole Life Journey - User Signals

Project: Whole Life Journey
Path: apps/users/signals.py
Purpose: Django signals for automatic user-related object creation

Description:
    Defines post_save signals that automatically create UserPreferences
    when a new user is created. This ensures every user always has an
    associated preferences object with default settings.

Signal Handlers:
    - create_user_preferences: Creates UserPreferences on new User creation
    - save_user_preferences: Ensures preferences are saved with user

Design Notes:
    These signals are connected in apps.py ready() method to avoid
    import issues during Django startup.

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserPreferences


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_preferences(sender, instance, created, **kwargs):
    """
    Automatically create UserPreferences when a new User is created.
    """
    if created:
        UserPreferences.objects.create(
            user=instance,
            theme=settings.WLJ_SETTINGS.get("DEFAULT_THEME", "minimal"),
        )


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_preferences(sender, instance, **kwargs):
    """
    Ensure UserPreferences is saved when User is saved.
    """
    try:
        instance.preferences.save()
    except UserPreferences.DoesNotExist:
        UserPreferences.objects.create(
            user=instance,
            theme=settings.WLJ_SETTINGS.get("DEFAULT_THEME", "minimal"),
        )
