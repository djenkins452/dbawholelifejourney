# ==============================================================================
# File: 0020_assistant_coaching_time_release_note.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Data migration for AI Assistant coaching style + time-aware urgency
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================

from django.db import migrations
from django.utils import timezone


def add_release_note(apps, schema_editor):
    """Add release note for AI Assistant coaching style and time-aware urgency."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    ReleaseNote.objects.get_or_create(
        title="AI Assistant: Smarter & Time-Aware",
        defaults={
            'description': (
                "Your AI Personal Assistant is now smarter and more personalized:\n\n"
                "**Coaching Style Integration**\n"
                "• The Assistant now uses your selected AI Coaching Style\n"
                "• Choose Direct, Gentle, Supportive, or other styles in Preferences\n"
                "• Consistent personality across Dashboard AI and Assistant\n\n"
                "**Time-Aware Urgency**\n"
                "• Knows what time it is in YOUR timezone\n"
                "• Increases urgency as your day progresses\n"
                "• Evening reminders: 'Only 3 hours left before bedtime'\n"
                "• Helps you prioritize what's still remaining\n\n"
                "**Focus on What's LEFT**\n"
                "• Shows remaining tasks, not completed ones\n"
                "• Time-sensitive nudges: '4 tasks still due today. 2 hours to go.'\n"
                "• Direct style example: '3 overdue. Handle them now.'"
            ),
            'entry_type': 'enhancement',
            'is_major': True,
            'is_published': True,
            'release_date': timezone.now().date(),
        }
    )


def remove_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title="AI Assistant: Smarter & Time-Aware").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_merge_20251230_0556"),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
