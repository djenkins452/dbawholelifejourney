# ==============================================================================
# File: 0015_fitness_tile_metrics_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Fitness Tile Metrics release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release note for Fitness Tile Metrics feature.

Features included:
- Fitness tile on Health page now shows summary statistics
- Workouts this week and this month counts
- Weekly workout duration totals
- Last workout date display
"""
from django.db import migrations


def add_fitness_tile_metrics_release_note(apps, schema_editor):
    """Add release note for Fitness Tile Metrics feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Fitness Tile Summary Metrics',
            'description': (
                'The Fitness tile on the Health page now displays summary statistics '
                'just like the other health tiles. See your workouts this week, '
                'workouts this month, total workout minutes, and when you last exercised - '
                'all at a glance without navigating away from the Health overview.'
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


def remove_fitness_tile_metrics_release_note(apps, schema_editor):
    """Remove the Fitness Tile Metrics release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Fitness Tile Summary Metrics',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_dashboard_tile_shortcuts_release_note'),
    ]

    operations = [
        migrations.RunPython(add_fitness_tile_metrics_release_note, remove_fitness_tile_metrics_release_note),
    ]
