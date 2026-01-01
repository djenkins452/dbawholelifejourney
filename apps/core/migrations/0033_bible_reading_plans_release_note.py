# ==============================================================================
# File: apps/core/migrations/0033_bible_reading_plans_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for Bible Reading Plans
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for Bible Reading Plans & Study Tools."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Bible Reading Plans & Study Tools").exists():
        ReleaseNote.objects.create(
            version="1.6.0",
            title="Bible Reading Plans & Study Tools",
            description=(
                "Grow in Scripture with new Bible reading plans and study tools! "
                "Choose from plans on topics like forgiveness, prayer, peace, and marriage, "
                "or read through the Gospel of John in 21 days. Track your daily progress "
                "and add reflections as you read. Plus, new study tools let you highlight "
                "verses in different colors, bookmark passages to return to, and create "
                "in-depth study notes. Go to Faith > Reading Plans to get started!"
            ),
            entry_type="feature",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=True
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Bible Reading Plans & Study Tools").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_dexcom_cgm_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
