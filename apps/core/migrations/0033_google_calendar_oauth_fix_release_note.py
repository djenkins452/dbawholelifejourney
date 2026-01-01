# ==============================================================================
# File: apps/core/migrations/0033_google_calendar_oauth_fix_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for Google Calendar OAuth fix
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for Google Calendar OAuth fix."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Google Calendar Connection Fix").exists():
        ReleaseNote.objects.create(
            version="1.5.1",
            title="Google Calendar Connection Fix",
            description=(
                "Fixed an issue preventing Google Calendar connection in production. "
                "Users can now connect their Google Calendar to sync Life module events. "
                "Go to Life > Calendar Settings to connect your calendar."
            ),
            entry_type="fix",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Google Calendar Connection Fix").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_dexcom_cgm_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
