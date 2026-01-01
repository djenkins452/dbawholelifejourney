# ==============================================================================
# File: apps/core/migrations/0030_journal_book_view_fix_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for Journal Book View fix
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for Journal Book View fix."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Journal Book View Fixed").exists():
        ReleaseNote.objects.create(
            version="1.4.4",
            title="Journal Book View Fixed",
            description=(
                "Fixed an issue where the Journal Book View wasn't displaying entries. "
                "You can now view your journal entries one at a time in a beautiful "
                "book-like format. Navigate between entries using the arrow buttons "
                "or keyboard arrow keys. Find it under Journal → Book View."
            ),
            entry_type="fix",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Journal Book View Fixed").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_sms_scheduler_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
