# ==============================================================================
# File: apps/core/migrations/0040_page_aware_assistant_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for page-aware assistant chat feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-11
# ==============================================================================
"""
Data migration to add What's New release note for the page-aware assistant chat feature.
The assistant can now understand context from the page you're viewing.
"""

from django.db import migrations
from datetime import date


def add_page_aware_assistant_release_note(apps, schema_editor):
    """Add release note for page-aware assistant chat."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    if not ReleaseNote.objects.filter(
        title='Smart Assistant: Page-Aware Context'
    ).exists():
        ReleaseNote.objects.create(
            title='Smart Assistant: Page-Aware Context',
            description=(
                'Your AI Assistant now understands what you\'re looking at! '
                'When you open the assistant chat, it captures the content of your current page. '
                'Ask questions like "help me with this scripture" or "explain this entry" - '
                'the assistant knows you\'re referring to what\'s on your screen. '
                'Works with Reading Plans, Journal entries, Tasks, Goals, Prayer Requests, and Health pages.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 11),
            is_published=True,
            is_major=True,
            version='',
            learn_more_url='',
        )


def remove_page_aware_assistant_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='Smart Assistant: Page-Aware Context'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0039_preferences_customization_release_notes'),
    ]

    operations = [
        migrations.RunPython(
            add_page_aware_assistant_release_note,
            remove_page_aware_assistant_release_note,
        ),
    ]
