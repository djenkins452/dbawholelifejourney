# ==============================================================================
# File: 0024_add_cascading_menu_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add What's New entry for cascading menu feature
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-31
# Last Updated: 2025-12-31
# ==============================================================================

from django.db import migrations
from datetime import date


def add_cascading_menu_release_note(apps, schema_editor):
    """Add a What's New entry for the cascading menu navigation feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    ReleaseNote.objects.get_or_create(
        title="Enhanced Navigation with Cascading Menus",
        defaults={
            'description': (
                "Navigate directly to any page with our new cascading menu system. "
                "Hover over main menu items on desktop (or tap on mobile) to reveal "
                "dropdown menus with quick access to all sub-pages. Health module now "
                "features an organized mega-menu with sections for Vitals, Medicine, "
                "Fitness, Nutrition, and Providers. Find what you need faster without "
                "visiting the module home page first."
            ),
            'entry_type': 'feature',
            'version': '',
            'release_date': date(2025, 12, 31),
            'is_published': True,
            'is_major': False,
        }
    )


def remove_cascading_menu_release_note(apps, schema_editor):
    """Remove the cascading menu release note on rollback."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="Enhanced Navigation with Cascading Menus").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_merge_20251231_0658"),
    ]

    operations = [
        migrations.RunPython(
            add_cascading_menu_release_note,
            remove_cascading_menu_release_note,
        ),
    ]
