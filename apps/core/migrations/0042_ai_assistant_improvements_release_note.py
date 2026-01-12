# ==============================================================================
# File: apps/core/migrations/0042_ai_assistant_improvements_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for AI assistant improvements
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# ==============================================================================
"""
Data migration to add What's New release note for AI assistant improvements:
- Auto-fetch verse text when saving via assistant
- Improved intent recognition for faith, journal, and life actions
"""

from django.db import migrations
from datetime import date


def add_ai_assistant_release_note(apps, schema_editor):
    """Add release note for AI assistant improvements."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    if not ReleaseNote.objects.filter(
        title='AI Assistant: Smarter Scripture & Action Recognition'
    ).exists():
        ReleaseNote.objects.create(
            title='AI Assistant: Smarter Scripture & Action Recognition',
            description=(
                'Your AI Assistant is now smarter! When you save a Bible verse, '
                'it automatically fetches the full verse text from the Bible API '
                'using your preferred translation. Plus, the assistant now better '
                'recognizes commands for saving verses, logging prayers, creating '
                'journal entries, and managing tasks - just tell it what you need!'
            ),
            entry_type='enhancement',
            release_date=date(2026, 1, 12),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )


def remove_ai_assistant_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='AI Assistant: Smarter Scripture & Action Recognition'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_journal_emotions_coppa_release_notes'),
    ]

    operations = [
        migrations.RunPython(
            add_ai_assistant_release_note,
            remove_ai_assistant_release_note,
        ),
    ]
