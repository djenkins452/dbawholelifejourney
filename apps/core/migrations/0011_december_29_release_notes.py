# ==============================================================================
# File: 0011_december_29_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add December 29, 2025 release notes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release notes for December 29, 2025 features.

Features included:
- Blood Pressure & Blood Oxygen tracking
- Medicine Refill Request status
- Default Fasting Type preference
- Dashboard Current Fast widget
- Default entry dates with user timezone
"""
from django.db import migrations


def add_december_29_release_notes(apps, schema_editor):
    """Add release notes for December 29, 2025 features."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Blood Pressure & Blood Oxygen Tracking',
            'description': (
                'Track your vital signs with new Blood Pressure (systolic/diastolic) and '
                'Blood Oxygen (SpO2) logging. Automatic categorization according to AHA '
                'guidelines shows Normal, Elevated, High, or Critical readings. View your '
                'latest readings and averages right on the Health home page.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': True,
        },
        {
            'title': 'Medicine Refill Request Tracking',
            'description': (
                'Never lose track of refill requests! When a medicine is running low, '
                'click "Request Refill" to mark it as requested. Dashboard shows "Refill '
                'Requested" status so you know the request is pending. Click "Refill '
                'Received" when your refill arrives.'
            ),
            'entry_type': 'enhancement',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Default Fasting Type Preference',
            'description': (
                'Set your preferred fasting protocol (16:8, 18:6, OMAD, etc.) in '
                'Preferences. When you start a new fast, your preferred type is '
                'automatically selected. Each type includes a helpful description of '
                'the fasting window and typical eating window.'
            ),
            'entry_type': 'enhancement',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Dashboard Fasting Widget',
            'description': (
                'See your current fast at a glance! A new widget on the dashboard shows '
                'your active fast with a real-time updating timer (hours:minutes:seconds), '
                'progress bar toward your target, and quick actions to end or view details.'
            ),
            'entry_type': 'enhancement',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': False,
        },
        {
            'title': 'Timezone-Aware Date Defaults',
            'description': (
                'All entry forms now default to YOUR local date based on your configured '
                'timezone. No more confusion about which day to select - journal entries, '
                'milestones, medicines, and life events all start with the right date.'
            ),
            'entry_type': 'fix',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': False,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_december_29_release_notes(apps, schema_editor):
    """Remove the December 29, 2025 release notes."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Blood Pressure & Blood Oxygen Tracking',
        'Medicine Refill Request Tracking',
        'Default Fasting Type Preference',
        'Dashboard Fasting Widget',
        'Timezone-Aware Date Defaults',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_dashboard_ai_release_note'),
    ]

    operations = [
        migrations.RunPython(add_december_29_release_notes, remove_december_29_release_notes),
    ]
