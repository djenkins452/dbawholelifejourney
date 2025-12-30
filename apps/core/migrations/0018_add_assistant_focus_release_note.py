# ==============================================================================
# File: 0018_add_assistant_focus_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration to add release note for AI Assistant focus update
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for AI Assistant task-focused update."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    ReleaseNote.objects.get_or_create(
        title="AI Assistant Now Task-Focused",
        defaults={
            'description': (
                "Your AI Personal Assistant has been updated to focus on what needs "
                "to be done, not what's already accomplished. The Assistant now:\n\n"
                "• Surfaces action items and things that need attention\n"
                "• Prioritizes overdue tasks and upcoming deadlines\n"
                "• Provides clear, actionable next steps\n"
                "• Keeps communication direct and efficient\n\n"
                "Positive feedback and celebrations now appear on your Dashboard, "
                "while the Assistant helps you stay focused and productive."
            ),
            'entry_type': 'enhancement',
            'is_major': False,
            'is_published': True,
            'release_date': timezone.now().date(),
        }
    )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="AI Assistant Now Task-Focused").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_merge_20251229_2105"),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
