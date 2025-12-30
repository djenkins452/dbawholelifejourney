# ==============================================================================
# File: 0014_assistant_chat_history_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add release note for Assistant chat history removal
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release note for removing chat history display on Assistant.
"""
from django.db import migrations


def add_chat_history_removal_note(apps, schema_editor):
    """Add release note for Assistant chat history removal."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    note_data = {
        'title': 'Cleaner Assistant Experience',
        'description': (
            'The Assistant page now starts fresh each time you visit. '
            'Previous chat history is no longer displayed, giving you a clean slate '
            'for each new conversation with your personal assistant.'
        ),
        'entry_type': 'enhancement',
        'release_date': date(2025, 12, 29),
        'is_published': True,
        'is_major': False,
    }

    # Only create if it doesn't already exist (idempotent)
    if not ReleaseNote.objects.filter(title=note_data['title']).exists():
        ReleaseNote.objects.create(**note_data)


def remove_chat_history_removal_note(apps, schema_editor):
    """Remove the chat history removal release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title='Cleaner Assistant Experience').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_merge_20251229_1954'),
    ]

    operations = [
        migrations.RunPython(add_chat_history_removal_note, remove_chat_history_removal_note),
    ]
