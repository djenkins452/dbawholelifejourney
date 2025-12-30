# ==============================================================================
# File: 0012_weight_nutrition_goals_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Weight & Nutrition Goals release notes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release notes for Weight & Nutrition Goals feature.

Features included:
- Weight Goal tracking with progress display
- Nutrition Goals with macro targets
- Dashboard progress indicators
"""
from django.db import migrations


def add_weight_nutrition_goals_release_notes(apps, schema_editor):
    """Add release notes for Weight & Nutrition Goals feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Weight & Nutrition Goals',
            'description': (
                'Set personal health targets and track your progress! In Preferences, you can '
                'now set a target weight (with optional deadline) and daily nutrition goals '
                'including calories and macro percentages (protein/carbs/fat). Your progress '
                'is displayed on the dashboard - the Health tile shows how close you are to '
                'your weight goal, and a new "Today\'s Nutrition" section shows your macro '
                'progress with visual progress bars.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': True,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_weight_nutrition_goals_release_notes(apps, schema_editor):
    """Remove the Weight & Nutrition Goals release notes."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Weight & Nutrition Goals',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_december_29_release_notes'),
    ]

    operations = [
        migrations.RunPython(add_weight_nutrition_goals_release_notes, remove_weight_nutrition_goals_release_notes),
    ]
