# ==============================================================================
# File: apps/core/migrations/0043_nutrition_scan_icons_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Adds What's New entry for nutrition scan icons feature
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-12
# ==============================================================================
"""
Data migration to add What's New release note for nutrition scan icons:
- Scan icons throughout nutrition flow
- Auto-detect meal type based on time of day
"""

from django.db import migrations
from datetime import date


def add_nutrition_scan_release_note(apps, schema_editor):
    """Add release note for nutrition scan icons feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    if not ReleaseNote.objects.filter(
        title='Quick Scan: Log Food Faster with Barcode Scanning'
    ).exists():
        ReleaseNote.objects.create(
            title='Quick Scan: Log Food Faster with Barcode Scanning',
            description=(
                'Scan food barcodes from anywhere in the Nutrition section! '
                'Look for the camera icon next to Log Food and each meal section. '
                'The app now auto-detects the meal type based on when you scan - '
                'breakfast in the morning, lunch midday, dinner in the evening. '
                'Plus, a new "Save & Scan" button lets you quickly log multiple items in a row.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 12),
            is_published=True,
            is_major=False,
            version='',
            learn_more_url='',
        )


def remove_nutrition_scan_release_note(apps, schema_editor):
    """Remove the release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(
        title='Quick Scan: Log Food Faster with Barcode Scanning'
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_ai_assistant_improvements_release_note'),
    ]

    operations = [
        migrations.RunPython(
            add_nutrition_scan_release_note,
            remove_nutrition_scan_release_note,
        ),
    ]
