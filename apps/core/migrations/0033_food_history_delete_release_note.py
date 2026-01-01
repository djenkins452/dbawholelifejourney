# ==============================================================================
# File: apps/core/migrations/0033_food_history_delete_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for food history delete button
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for food history delete button."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Delete Food Entries from History").exists():
        ReleaseNote.objects.create(
            version="1.5.1",
            title="Delete Food Entries from History",
            description=(
                "You can now delete food entries directly from the Food History page! "
                "Each entry now has a Delete button next to View and Edit, making it "
                "easier to manage your nutrition tracking without navigating to the "
                "detail page first."
            ),
            entry_type="improvement",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Delete Food Entries from History").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_dexcom_cgm_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
