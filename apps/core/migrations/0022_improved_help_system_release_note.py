# ==============================================================================
# File: apps/core/migrations/0022_improved_help_system_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Add release note for improved help system
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_notes(apps, schema_editor):
    """Add release note for improved help system."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Create release note for improved help system
    ReleaseNote.objects.get_or_create(
        title="Improved Help System",
        defaults={
            'description': (
                "The in-app help system has been completely rewritten with more "
                "detailed, valuable content.\n\n"
                "**What's New:**\n"
                "- **'Why Use This Feature'** - Each help topic now explains the value "
                "and reason to use each feature, not just how to use it\n"
                "- **Dashboard & AI Connection** - Help content explains how each feature "
                "feeds into your Dashboard and AI insights\n"
                "- **New Help Topics** - Added detailed help for Nutrition, Medicine, "
                "Camera Scan, Personal Assistant, SMS Notifications, Vitals, and Medical Providers\n"
                "- **Tables & Visual Guides** - Easier-to-read format with tables showing "
                "what data you log and what insights you get\n"
                "- **Related Features** - Each help topic links to related features so you "
                "can understand how everything connects\n\n"
                "Click the **?** icon on any page to see the improved help content."
            ),
            'entry_type': 'enhancement',
            'release_date': timezone.now().date(),
            'is_published': True,
            'is_major': True,
        }
    )


def remove_release_notes(apps, schema_editor):
    """Remove release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Improved Help System").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_medicine_timezone_fix_release_note'),
    ]

    operations = [
        migrations.RunPython(add_release_notes, remove_release_notes),
    ]
