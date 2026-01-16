# ==============================================================================
# File: apps/admin_console/migrations/0018_reset_teaching_destinations_loader.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Reset teaching_destinations loader to reload expanded fixture
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-16
# ==============================================================================
"""
Data migration to reset the teaching_destinations loader so it reloads
with the expanded fixture containing 55 destinations (up from 27).

New destinations added:
- Scan (camera/barcode)
- Finance (dashboard, budgets, goals)
- Life (inventory, pets, documents, events, maintenance)
- Health vitals (BP, HR, steps, SpO2, providers, templates, PRs, quick log)
- Faith (verse, scripture, milestones, study tools)
- Purpose (direction, intentions, reflections)
- Core (What's New, journal prompts, SMS history, billing)
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
        ('admin_console', '0017_update_task_236_with_implementation_details'),
    ]

    operations = [
        migrations.RunPython(
            reset_teaching_destinations_loader,
            noop,
        ),
    ]
