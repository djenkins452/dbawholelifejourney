# ==============================================================================
# File: apps/core/migrations/0029_sms_scheduler_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for SMS scheduler fix
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for SMS scheduler fix."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="SMS Reminders Now Working").exists():
        ReleaseNote.objects.create(
            version="1.4.3",
            title="SMS Reminders Now Working",
            description=(
                "Fixed an issue where SMS medicine reminders were not being sent. "
                "The notification system now includes an automatic background scheduler "
                "that sends your reminders without any manual intervention. "
                "Your medicine reminders will now arrive at the scheduled times!"
            ),
            entry_type="fix",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="SMS Reminders Now Working").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_medicine_log_edit_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
