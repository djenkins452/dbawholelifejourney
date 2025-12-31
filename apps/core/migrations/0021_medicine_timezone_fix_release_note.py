# ==============================================================================
# File: 0021_medicine_timezone_fix_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add release note for medicine timezone fix
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
Data migration to add release note for medicine 'taken at' timezone fix.
"""
from django.db import migrations


def add_medicine_timezone_fix_note(apps, schema_editor):
    """Add release note for medicine timezone fix."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    note_data = {
        'title': 'Medicine Time Display Fixed',
        'description': (
            'Fixed an issue where medicine "taken at" times were showing in UTC instead of '
            'your local timezone. Medicines taken on time were incorrectly showing as "Taken Late" '
            'for users in timezones behind UTC. Times now correctly display in your configured timezone.'
        ),
        'entry_type': 'fix',
        'release_date': date(2025, 12, 30),
        'is_published': True,
        'is_major': False,
    }

    # Only create if it doesn't already exist (idempotent)
    if not ReleaseNote.objects.filter(title=note_data['title']).exists():
        ReleaseNote.objects.create(**note_data)


def remove_medicine_timezone_fix_note(apps, schema_editor):
    """Remove the medicine timezone fix release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title='Medicine Time Display Fixed').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_assistant_coaching_time_release_note'),
    ]

    operations = [
        migrations.RunPython(add_medicine_timezone_fix_note, remove_medicine_timezone_fix_note),
    ]
