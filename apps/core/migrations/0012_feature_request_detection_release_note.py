# ==============================================================================
# File: apps/core/migrations/0012_feature_request_detection_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for AI Assistant feature request detection
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-10
# ==============================================================================
"""
Data migration to add a What's New release note for the
AI Assistant feature request detection feature.
"""

from django.db import migrations
from datetime import date


def add_feature_request_release_note(apps, schema_editor):
    """Add the feature request detection release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this release note already exists (by title)
    if not ReleaseNote.objects.filter(
        title='AI Assistant Listens to Your Wishes'
    ).exists():
        ReleaseNote.objects.create(
            title='AI Assistant Listens to Your Wishes',
            description=(
                'The AI Assistant now captures your feature requests automatically! '
                'When you say things like "I wish I could..." or "I want to be able to...", '
                'your feedback is recorded and sent to the development team for review. '
                'Your voice helps shape the future of Whole Life Journey.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 10),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )


def remove_feature_request_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='AI Assistant Listens to Your Wishes'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_add_sms_models'),
    ]

    operations = [
        migrations.RunPython(
            add_feature_request_release_note,
            remove_feature_request_release_note,
        ),
    ]
