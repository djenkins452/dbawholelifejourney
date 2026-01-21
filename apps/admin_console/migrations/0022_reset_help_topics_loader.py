# ==============================================================================
# File: apps/admin_console/migrations/0022_reset_help_topics_loader.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reset help_topics loader to reload fixture with specific topics
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-21
# ==============================================================================
"""
Data migration to reset the help_topics loader so it reloads with the
updated fixture containing specific help topics for Health sub-pages.

New/updated topics that will be loaded:
- HEALTH_HEART_RATE - Heart Rate specific help (was falling back to HEALTH_HOME)
- HEALTH_WEIGHT - Weight tracking help
- HEALTH_FASTING - Fasting tracking help
- HEALTH_FITNESS - Fitness/workout help

This fixes the issue where contextual help for Heart Rate was showing
generic health module content instead of Heart Rate specific content.
"""

from django.db import migrations


def reset_help_topics_loader(apps, schema_editor):
    """Reset the help_topics loader so it runs again on next deploy."""
    DataLoadConfig = apps.get_model('admin_console', 'DataLoadConfig')

    try:
        config = DataLoadConfig.objects.get(loader_name='help_topics')
        config.is_loaded = False
        config.save(update_fields=['is_loaded'])
    except DataLoadConfig.DoesNotExist:
        # Not yet loaded, nothing to reset
        pass


def noop(apps, schema_editor):
    """No-op for reverse migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admin_console', '0021_notification_system'),
    ]

    operations = [
        migrations.RunPython(
            reset_help_topics_loader,
            noop,
        ),
    ]
