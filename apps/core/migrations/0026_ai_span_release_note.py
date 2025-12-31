# ==============================================================================
# File: apps/core/migrations/0026_ai_span_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for AI Span enhancement
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations


def add_release_note(apps, schema_editor):
    """Add release note for AI Span comprehensive context enhancement."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Smarter AI Insights").exists():
        ReleaseNote.objects.create(
            version="1.4.0",
            title="Smarter AI Insights",
            description=(
                "Your AI coach now sees your complete picture - Word of the Year, "
                "goals, intentions, prayers, projects, weight goals, nutrition progress, "
                "and more. Dashboard messages are now deeply personalized to your whole life journey."
            ),
            entry_type="feature",
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Smarter AI Insights").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0025_merge_20251231_0721'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
