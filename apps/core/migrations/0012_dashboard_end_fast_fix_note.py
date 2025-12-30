# ==============================================================================
# File: 0012_dashboard_end_fast_fix_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add release note for Dashboard End Fast fix
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release note for Dashboard End Fast button fix.
"""
from django.db import migrations


def add_end_fast_fix_note(apps, schema_editor):
    """Add release note for End Fast button fix."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    note_data = {
        'title': 'Dashboard End Fast Button Fixed',
        'description': (
            'Fixed an issue where clicking "End Fast" on the dashboard would show an error. '
            'The button now works correctly to end your active fast.'
        ),
        'entry_type': 'fix',
        'release_date': date(2025, 12, 29),
        'is_published': True,
        'is_major': False,
    }

    # Only create if it doesn't already exist (idempotent)
    if not ReleaseNote.objects.filter(title=note_data['title']).exists():
        ReleaseNote.objects.create(**note_data)


def remove_end_fast_fix_note(apps, schema_editor):
    """Remove the End Fast fix release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title='Dashboard End Fast Button Fixed').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_december_29_release_notes'),
    ]

    operations = [
        migrations.RunPython(add_end_fast_fix_note, remove_end_fast_fix_note),
    ]
