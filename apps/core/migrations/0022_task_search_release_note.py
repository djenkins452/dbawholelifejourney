# ==============================================================================
# File: 0022_task_search_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Task Search release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Data migration to add release note for Task Search feature.

Features included:
- Search bar on task list page
- Search by title and notes content
- Works with existing filters
"""
from django.db import migrations


def add_task_search_release_note(apps, schema_editor):
    """Add release note for Task Search feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Task Search',
            'description': (
                'You can now search through your tasks! A new search bar at the top of the '
                'task list lets you quickly find tasks by title or notes content. Search works '
                'together with existing filters (Active/Completed, Priority), so you can search '
                'within a filtered view. Results show a count of matching tasks.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 31),
            'is_published': True,
            'is_major': False,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_task_search_release_note(apps, schema_editor):
    """Remove the Task Search release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Task Search',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_medicine_timezone_fix_release_note'),
    ]

    operations = [
        migrations.RunPython(add_task_search_release_note, remove_task_search_release_note),
    ]
