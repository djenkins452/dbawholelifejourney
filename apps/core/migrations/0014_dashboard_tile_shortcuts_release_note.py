# ==============================================================================
# File: 0014_dashboard_tile_shortcuts_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Dashboard Tile Shortcuts release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release note for Dashboard Tile Shortcuts feature.

Features included:
- Clickable quick stat tiles on dashboard
- Direct navigation to Journal, Tasks, Prayers, Medicine, and Workouts
"""
from django.db import migrations


def add_dashboard_tile_shortcuts_release_note(apps, schema_editor):
    """Add release note for Dashboard Tile Shortcuts feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Dashboard Tile Shortcuts',
            'description': (
                'The quick stat tiles at the top of your dashboard are now clickable! '
                'Tap on any tile to jump directly to its detail page: Journal Streak opens '
                'your journal entries, Tasks Today opens your task list, Medicine Doses '
                'opens your medicine tracker, and Workouts opens your workout history.'
            ),
            'entry_type': 'enhancement',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': False,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_dashboard_tile_shortcuts_release_note(apps, schema_editor):
    """Remove the Dashboard Tile Shortcuts release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Dashboard Tile Shortcuts',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_merge_20251229_1954'),
    ]

    operations = [
        migrations.RunPython(add_dashboard_tile_shortcuts_release_note, remove_dashboard_tile_shortcuts_release_note),
    ]
