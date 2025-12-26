"""
User Signals - Automatically create related objects when user is created.
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
