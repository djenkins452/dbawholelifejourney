# ==============================================================================
# File: apps/core/migrations/0045_nutrition_meal_subtotals_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for nutrition meal subtotals feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-14
# ==============================================================================
"""
Data migration to add What's New release note for nutrition meal subtotals:
- Shows calories, protein, carbs, fat for each meal section
"""

from django.db import migrations
from datetime import date


def add_nutrition_subtotals_release_note(apps, schema_editor):
    """Add release note for nutrition meal subtotals feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    if not ReleaseNote.objects.filter(
        title='Nutrition: Meal Subtotals'
    ).exists():
        ReleaseNote.objects.create(
            title='Nutrition: Meal Subtotals',
            description=(
                'Each meal section (Breakfast, Lunch, Dinner, Snacks) now shows '
                'a subtotal with calories, protein, carbs, and fat. See your '
                'nutritional breakdown at a glance for each meal without scrolling!'
            ),
            entry_type='enhancement',
            release_date=date(2026, 1, 14),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )


def remove_nutrition_subtotals_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='Nutrition: Meal Subtotals'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0044_apirequestlog'),
    ]

    operations = [
        migrations.RunPython(
            add_nutrition_subtotals_release_note,
            remove_nutrition_subtotals_release_note,
        ),
    ]
