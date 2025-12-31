# ==============================================================================
# File: 0022_sms_fix_task_search_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add release notes for SMS fix and task search
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Data migration to add release notes for SMS preferences fix and task search feature.
"""
from django.db import migrations


def add_release_notes(apps, schema_editor):
    """Add release notes for SMS fix and task search."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    notes = [
        {
            'title': 'SMS Preferences Now Save Correctly',
            'description': (
                'Fixed an issue where changes to SMS notification settings were not being saved. '
                'Your SMS preferences (enabled, consent, reminder categories, quiet hours) will '
                'now save properly when you update your preferences.'
            ),
            'entry_type': 'fix',
            'release_date': date(2025, 12, 31),
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Task Search Feature',
            'description': (
                'You can now search through your tasks! The Tasks page now includes a search bar '
                'that lets you find tasks by title, notes, or project name. Filter buttons also '
                'show task counts so you can see how many tasks are in each category.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 31),
            'is_published': True,
            'is_major': False,
        },
    ]

    for note_data in notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_release_notes(apps, schema_editor):
    """Remove the release notes."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title__in=['SMS Preferences Now Save Correctly', 'Task Search Feature']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_medicine_timezone_fix_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_notes, remove_release_notes),
    ]
