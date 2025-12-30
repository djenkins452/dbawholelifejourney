# ==============================================================================
# File: 0013_medical_providers_release_notes.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Medical Providers release notes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release notes for Medical Providers feature.

Features included:
- Store and manage medical provider contact information
- AI-powered lookup to auto-populate provider details
- Track supporting staff (doctors, nurses, PAs) for each provider
"""
from django.db import migrations


def add_medical_providers_release_notes(apps, schema_editor):
    """Add release notes for Medical Providers feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Medical Providers Tracking',
            'description': (
                'Keep all your healthcare provider information in one place! Add doctors, '
                'specialists, dentists, and other medical providers with their contact details, '
                'addresses, and patient portal information. Use the AI Lookup feature to '
                'automatically find and fill in provider contact details - just enter the '
                'provider name and let AI do the rest. You can also track supporting staff '
                '(nurses, physician assistants, receptionists) for each provider with their '
                'direct contact information.'
            ),
            'entry_type': 'feature',
            'release_date': date(2025, 12, 29),
            'is_published': True,
            'is_major': True,
        },
    ]

    for note_data in release_notes:
        # Only create if it doesn't already exist (idempotent)
        if not ReleaseNote.objects.filter(title=note_data['title']).exists():
            ReleaseNote.objects.create(**note_data)


def remove_medical_providers_release_notes(apps, schema_editor):
    """Remove the Medical Providers release notes."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Medical Providers Tracking',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_weight_nutrition_goals_release_notes'),
    ]

    operations = [
        migrations.RunPython(add_medical_providers_release_notes, remove_medical_providers_release_notes),
    ]
