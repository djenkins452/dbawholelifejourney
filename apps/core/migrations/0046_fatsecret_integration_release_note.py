# ==============================================================================
# File: apps/core/migrations/0046_fatsecret_integration_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for FatSecret Premier integration
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-15
# ==============================================================================
"""
Data migration to add What's New release note for FatSecret integration:
- Improved barcode scanning with FatSecret database
- AI food image recognition
- Better food search results
"""

from django.db import migrations
from datetime import date


def add_fatsecret_release_note(apps, schema_editor):
    """Add release note for FatSecret Premier integration."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    if not ReleaseNote.objects.filter(
        title='Improved Food Recognition'
    ).exists():
        ReleaseNote.objects.create(
            title='Improved Food Recognition',
            description=(
                'Food tracking just got smarter! We\'ve upgraded to FatSecret\'s '
                'Premier database with 1.9 million foods. Barcode scanning is now '
                'faster and more accurate, and our new AI can identify food from '
                'photos - just snap a picture of your meal and we\'ll suggest the '
                'nutrition info!'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 15),
            is_published=True,
            is_major=True,
            version='',
            learn_more_url='',
        )


def remove_fatsecret_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='Improved Food Recognition'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_nutrition_meal_subtotals_release_note'),
    ]

    operations = [
        migrations.RunPython(
            add_fatsecret_release_note,
            remove_fatsecret_release_note,
        ),
    ]
