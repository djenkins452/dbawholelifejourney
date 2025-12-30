# ==============================================================================
# File: 0017_personal_assistant_module_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add Personal Assistant Module release note
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================
"""
Data migration to add release note for Personal Assistant Module feature.

Personal Assistant is now a separate module with its own consent, separate from
general AI Features. This allows users to enable AI features without the Personal
Assistant, and requires explicit consent for the Assistant's deeper data access.
"""
from django.db import migrations


def add_personal_assistant_module_release_note(apps, schema_editor):
    """Add release note for Personal Assistant Module feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    from datetime import date

    release_notes = [
        {
            'title': 'Personal Assistant Module',
            'description': (
                'The Personal Assistant is now a separate module with enhanced privacy controls. '
                'You can enable general AI features (insights, camera scanning) without the Personal Assistant, '
                'and the Assistant requires its own explicit consent for deeper data access. '
                'Enable the Personal Assistant in Preferences under AI Features to get personalized daily priorities, '
                'celebrate your wins, and receive gentle accountability based on your complete journey.'
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


def remove_personal_assistant_module_release_note(apps, schema_editor):
    """Remove the Personal Assistant Module release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    titles = [
        'Personal Assistant Module',
    ]
    ReleaseNote.objects.filter(title__in=titles).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0016_merge_medical_providers'),
    ]

    operations = [
        migrations.RunPython(add_personal_assistant_module_release_note, remove_personal_assistant_module_release_note),
    ]
