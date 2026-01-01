# ==============================================================================
# File: apps/core/migrations/0030_weight_loss_graph_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Migration to add What's New release note for weight loss graph feature
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for weight loss graph feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if this note already exists
    if not ReleaseNote.objects.filter(title="Weight Progress Chart").exists():
        ReleaseNote.objects.create(
            version="1.4.4",
            title="Weight Progress Chart",
            description=(
                "See your weight journey at a glance! The Weight History page now includes "
                "an interactive progress chart showing your weight over time. Plus, a new "
                "'Total Change' stat shows exactly how much you've lost (or gained) since "
                "your first entry. Keep up the great work on your health goals!"
            ),
            entry_type="feature",
            release_date=timezone.now().date(),
            is_published=True,
            is_major=False
        )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Weight Progress Chart").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_sms_scheduler_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
