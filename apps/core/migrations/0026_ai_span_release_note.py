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
            summary=(
                "Your AI coach now sees your complete picture - Word of the Year, "
                "goals, intentions, prayers, projects, weight goals, nutrition progress, "
                "and more. Dashboard messages are now deeply personalized to your journey."
            ),
            description=(
                "## Enhanced AI Understanding\n\n"
                "The AI now reads and applies your full life context when generating insights:\n\n"
                "**Purpose & Direction:**\n"
                "- Your Word of the Year and annual theme\n"
                "- Active life goals with domain context\n"
                "- Change intentions you're working on\n\n"
                "**Faith Journey:**\n"
                "- Your memory verse and recent Scripture study\n"
                "- Active and answered prayers\n"
                "- Faith milestones\n\n"
                "**Life & Tasks:**\n"
                "- Priority projects and their progress\n"
                "- Tasks due today and overdue items\n"
                "- Today's calendar events\n\n"
                "**Health Progress:**\n"
                "- Weight goal progress\n"
                "- Today's nutrition vs your goals\n"
                "- Workout activity and personal records\n"
                "- Medicine adherence\n\n"
                "Your AI coach can now reference your Word of the Year, encourage specific goals, "
                "and provide truly personalized guidance based on your full life picture."
            ),
            release_type="feature",
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
