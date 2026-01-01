# ==============================================================================
# File: apps/core/migrations/0032_dexcom_cgm_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for Dexcom CGM integration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for Dexcom CGM integration."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Dexcom CGM Integration").exists():
        ReleaseNote.objects.create(
            version="1.5.0",
            title="Dexcom CGM Integration",
            description=(
                "Connect your Dexcom Continuous Glucose Monitor to automatically sync "
                "blood glucose readings! The new Glucose Dashboard shows your current reading "
                "with trend arrows, Time in Range stats, and a 24-hour chart. Go to Health > "
                "Blood Glucose and click 'Connect Dexcom' to get started. Your CGM data will "
                "sync automatically, helping you track your glucose management effortlessly."
            ),
            entry_type="feature",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=True
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Dexcom CGM Integration").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_merge_20251231_2325'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
