# ==============================================================================
# File: apps/core/migrations/0028_medicine_log_edit_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for medicine log edit feature
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for medicine log edit feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Edit Medicine Taken Time").exists():
        ReleaseNote.objects.create(
            version="1.4.2",
            title="Edit Medicine Taken Time",
            description=(
                "Took your medicine on time but forgot to log it? "
                "Now you can edit the 'taken at' time on any medicine log entry. "
                "Look for the Edit link on the Medicine Home page or History page. "
                "The system will automatically recalculate whether you were on time or late."
            ),
            entry_type="feature",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Edit Medicine Taken Time").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_menu_reorganization_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
