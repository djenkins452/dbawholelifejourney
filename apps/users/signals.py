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
from django.utils import timezone

from .models import UserPreferences


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_preferences(sender, instance, created, **kwargs):
    """
    Automatically create UserPreferences when a new User is created.

    Also creates UserReleaseNoteView with current timestamp so new users
    don't see existing "What's New" items - those features aren't new to them.
    """
    if created:
        UserPreferences.objects.create(
            user=instance,
            theme=settings.WLJ_SETTINGS.get("DEFAULT_THEME", "minimal"),
        )

        # Mark all existing release notes as "seen" for new users
        # They'll only see release notes added after they signed up
        from apps.core.models import UserReleaseNoteView

        UserReleaseNoteView.objects.create(
            user=instance,
            last_viewed_at=timezone.now(),
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


@receiver(post_save, sender=UserPreferences)
def sync_module_preferences_on_save(sender, instance, **kwargs):
    """
    Guarantee UserModulePreference rows exist and are synced for every module
    that has a preference_field bridge.

    On every UserPreferences save:
    1. For each active ModuleDefinition with a preference_field:
       - get_or_create the UserModulePreference row (guarantees it exists)
       - Set is_enabled to match the UserPreferences field value
    2. Invalidate nav cache if anything changed

    This eliminates reliance on lazy initialization (initialize_for_user).
    Module enablement is immediate and deterministic.
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        from apps.users.models import ModuleDefinition, UserModulePreference

        modules_with_bridge = ModuleDefinition.objects.filter(
            is_active=True,
            preference_field__gt='',
        )

        changed = False
        for module in modules_with_bridge:
            pref_value = getattr(instance, module.preference_field, None)
            if pref_value is None:
                continue

            ump, created = UserModulePreference.objects.get_or_create(
                user=instance.user,
                module=module,
                defaults={
                    'is_enabled': pref_value,
                    'sort_order': module.default_order,
                },
            )

            if created:
                changed = True
            elif ump.is_enabled != pref_value:
                ump.is_enabled = pref_value
                ump.save(update_fields=['is_enabled'])
                changed = True

        if changed:
            from apps.core.context_processors import invalidate_navigation_cache
            invalidate_navigation_cache(instance.user_id)

    except Exception:
        logger.warning("Failed to sync module preferences for user %s", instance.user_id, exc_info=True)


@receiver(post_save, sender=UserPreferences)
def auto_enable_cycle_tracking_for_female(sender, instance, **kwargs):
    """
    Auto-enable cycle tracking when a user sets their gender to female.

    Behavior:
    - If gender is 'female', create CycleSettings with cycle_tracking_enabled=True
    - If CycleSettings already exists, respect existing settings (don't override)
    - If gender changes FROM female to something else, do NOT delete CycleSettings
    - For male/prefer_not_to_say/None, do NOT auto-create CycleSettings
    """
    if instance.gender == "female":
        from apps.health.models import CycleSettings

        # get_or_create: only creates if doesn't exist, respects existing settings
        CycleSettings.objects.get_or_create(
            user=instance.user,
            defaults={"cycle_tracking_enabled": True},
        )
