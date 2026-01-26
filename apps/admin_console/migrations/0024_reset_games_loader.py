# ==============================================================================
# File: apps/admin_console/migrations/0024_reset_games_loader.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reset games loader to reload fixture with timestamps
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-26
# ==============================================================================
"""
Data migration to reset the games loader so it reloads with the
updated fixture containing created_at/updated_at timestamps.

The initial fixture was missing timestamps which caused a PostgreSQL
not-null constraint violation in production.
"""

from django.db import migrations


def reset_games_loader(apps, schema_editor):
    """Reset the games loader so it runs again on next deploy."""
    DataLoadConfig = apps.get_model('admin_console', 'DataLoadConfig')

    try:
        config = DataLoadConfig.objects.get(loader_name='games')
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
        ('admin_console', '0023_add_system_announcements'),
    ]

    operations = [
        migrations.RunPython(
            reset_games_loader,
            noop,
        ),
    ]
