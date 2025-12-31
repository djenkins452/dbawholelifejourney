# ==============================================================================
# File: apps/core/migrations/0027_menu_reorganization_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for menu reorganization
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for menu navigation reorganization."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Improved Menu Organization").exists():
        ReleaseNote.objects.create(
            version="1.4.1",
            title="Improved Menu Organization",
            description=(
                "Fasting is now under the Nutrition menu where it belongs. "
                "Significant Events has been added to the Life menu for easy access to birthdays and anniversaries."
            ),
            entry_type="enhancement",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Improved Menu Organization").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_ai_span_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
