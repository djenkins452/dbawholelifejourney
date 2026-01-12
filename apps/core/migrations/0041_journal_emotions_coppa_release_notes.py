# ==============================================================================
# File: apps/core/migrations/0041_journal_emotions_coppa_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entries for Journal Emotions and COPPA compliance
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# ==============================================================================
"""
Data migration to add What's New release notes for:
- Journal Emotions multi-select feature
- COPPA age verification and updated Terms/Privacy
"""

from django.db import migrations
from datetime import date


def add_release_notes(apps, schema_editor):
    """Add release notes for recent features."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Journal Emotions Multi-Select Feature
    if not ReleaseNote.objects.filter(
        title='Journal Emotions: Express How You Really Feel'
    ).exists():
        ReleaseNote.objects.create(
            title='Journal Emotions: Express How You Really Feel',
            description=(
                'You can now select multiple emotions for each journal entry! '
                'Choose from 14 emotions including Happy, Sad, Anxious, Excited, Grateful, and more. '
                'Your selected emotions appear as emoji badges on your entries, '
                'helping you track emotional patterns over time.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 12),
            is_published=True,
            is_major=True,
            version='',
            learn_more_url='',
        )

    # COPPA Age Verification
    if not ReleaseNote.objects.filter(
        title='Updated Terms of Service & Privacy Policy'
    ).exists():
        ReleaseNote.objects.create(
            title='Updated Terms of Service & Privacy Policy',
            description=(
                'We\'ve updated our Terms of Service (v1.1) and Privacy Policy '
                'to include enhanced COPPA compliance and age verification. '
                'New accounts now require date of birth to ensure users are 13 or older. '
                'Please review the updated terms when prompted.'
            ),
            entry_type='security',
            release_date=date(2026, 1, 12),
            is_published=True,
            is_major=False,
            version='1.1',
            learn_more_url='/terms/',
        )


def remove_release_notes(apps, schema_editor):
    """Remove the release notes on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title__in=[
            'Journal Emotions: Express How You Really Feel',
            'Updated Terms of Service & Privacy Policy',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0040_page_aware_assistant_release_note'),
    ]

    operations = [
        migrations.RunPython(
            add_release_notes,
            remove_release_notes,
        ),
    ]
