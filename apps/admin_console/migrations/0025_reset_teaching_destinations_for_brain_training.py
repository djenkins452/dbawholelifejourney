# ==============================================================================
# File: apps/admin_console/migrations/0025_reset_teaching_destinations_for_brain_training.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reset teaching destinations loader to add Brain Training entries
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-26
# ==============================================================================
"""
Data migration to reset the teaching_destinations loader so it reloads with
new Brain Training destinations added to the fixture.
"""

from django.db import migrations


def reset_teaching_destinations_loader(apps, schema_editor):
    """Reset the teaching_destinations loader so it runs again on next deploy."""
    DataLoadConfig = apps.get_model('admin_console', 'DataLoadConfig')

    try:
        config = DataLoadConfig.objects.get(loader_name='teaching_destinations')
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
        ('admin_console', '0024_reset_games_loader'),
    ]

    operations = [
        migrations.RunPython(
            reset_teaching_destinations_loader,
            noop,
        ),
    ]
