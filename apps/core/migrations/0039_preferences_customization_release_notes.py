# ==============================================================================
# File: apps/core/migrations/0039_preferences_customization_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entries for Preferences redesign and feature toggles
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-11
# ==============================================================================
"""
Data migration to add What's New release notes for:
1. Preferences page accordion redesign
2. AI Profile nudge system
3. Customize Features (sub-feature toggles)
"""

from django.db import migrations
from datetime import date


def add_preferences_release_notes(apps, schema_editor):
    """Add release notes for preferences customization features."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # 1. Preferences Page Redesign
    if not ReleaseNote.objects.filter(
        title='Redesigned Preferences Page'
    ).exists():
        ReleaseNote.objects.create(
            title='Redesigned Preferences Page',
            description=(
                'The Preferences page has been completely redesigned with collapsible '
                'sections for easier navigation. Find your settings faster with organized '
                'groups like Display, Modules, AI Features, Notifications, and Privacy.'
            ),
            entry_type='enhancement',
            release_date=date(2026, 1, 11),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )

    # 2. AI Profile Nudge
    if not ReleaseNote.objects.filter(
        title='AI Profile Setup Assistant'
    ).exists():
        ReleaseNote.objects.create(
            title='AI Profile Setup Assistant',
            description=(
                'New to Whole Life Journey? A friendly reminder on your dashboard will '
                'help you set up your AI Profile. Answer a few quick questions in our '
                'guided wizard and get more personalized insights from your AI coach.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 11),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )

    # 3. Customize Features
    if not ReleaseNote.objects.filter(
        title='Customize Your Features'
    ).exists():
        ReleaseNote.objects.create(
            title='Customize Your Features',
            description=(
                'You can now show or hide specific features within each module! '
                'Visit Preferences > Customize Features to toggle individual items like '
                'Blood Pressure tracking, Recipe management, or Writing Prompts. '
                'Your data is always preserved - hidden features can be re-enabled anytime.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 11),
            is_published=True,
            is_major=True,  # This is a significant feature
            version='',
            learn_more_url='',
        )


def remove_preferences_release_notes(apps, schema_editor):
    """Remove the release notes on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title__in=[
            'Redesigned Preferences Page',
            'AI Profile Setup Assistant',
            'Customize Your Features',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_feature_request_detection_release_note'),
    ]

    operations = [
        migrations.RunPython(
            add_preferences_release_notes,
            remove_preferences_release_notes,
        ),
    ]
