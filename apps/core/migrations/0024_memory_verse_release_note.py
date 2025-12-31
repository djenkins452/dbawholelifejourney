# ==============================================================================
# File: 0024_memory_verse_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Memory Verse release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================
"""
Data migration to add release note for Memory Verse feature.

Features included:
- Mark saved Scripture as Memory Verse
- Display Memory Verse at top of Dashboard
- One memory verse at a time per user
"""
from django.db import migrations


def add_memory_verse_release_note(apps, schema_editor):
    """Add release note for Memory Verse feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Memory Verse on Dashboard',
            'description': (
                'Memorizing Scripture? Now you can mark any saved verse as your "Memory Verse" '
                'and it will display prominently at the top of your Dashboard! Go to Faith → Scripture, '
                'click the star button on any verse to set it as your memory verse. Only one verse '
                'can be your memory verse at a time - perfect for focused memorization practice.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 31),
            'is_published': True,
            'is_major': True,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_memory_verse_release_note(apps, schema_editor):
    """Remove the Memory Verse release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Memory Verse on Dashboard',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_merge_20251231_0643'),
    ]

    operations = [
        migrations.RunPython(add_memory_verse_release_note, remove_memory_verse_release_note),
    ]
