# ==============================================================================
# File: 0010_dashboard_ai_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Dashboard AI Personal Assistant release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add Dashboard AI Personal Assistant to What's New.

This creates a release note entry that will be shown to users in the
What's New popup when they log in after this deployment.
"""
from django.db import migrations


def add_dashboard_ai_release_note(apps, schema_editor):
    """Add Dashboard AI Personal Assistant release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    # Only create if it doesn't already exist
    if not ReleaseNote.objects.filter(title='AI Personal Assistant').exists():
        ReleaseNote.objects.create(
            title='AI Personal Assistant',
            description=(
                'Meet your new personal life assistant! Get daily priorities based on your '
                'goals and intentions, celebrate your wins, and receive gentle accountability '
                'nudges. Features weekly/monthly trend analysis, personalized reflection prompts '
                'for journaling, and a conversational interface to explore your journey. '
                'Access it from the Assistant menu item.'
            ),
            entry_type='feature',
            release_date=date(2025, 12, 29),
            is_published=True,
            is_major=True,
        )


def remove_dashboard_ai_release_note(apps, schema_editor):
    """Remove the Dashboard AI release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title='AI Personal Assistant').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_load_release_notes'),
    ]

    operations = [
        migrations.RunPython(add_dashboard_ai_release_note, remove_dashboard_ai_release_note),
    ]
