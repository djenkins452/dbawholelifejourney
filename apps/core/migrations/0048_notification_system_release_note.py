# ==============================================================================
# Migration: 0048_notification_system_release_note
# Description: Add What's New entry for the Notification System feature
# ==============================================================================

from datetime import date
from django.db import migrations


def add_release_note(apps, schema_editor):
    """Add the Notification System release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Only create if it doesn't exist
    if not ReleaseNote.objects.filter(title='Notification System').exists():
        ReleaseNote.objects.create(
            title='Notification System',
            description=(
                'Stay on top of what matters! A new notification bell in the header shows '
                'your pending reminders, tasks due, prayer reminders, and more. '
                'Configure what you want to be notified about and choose between '
                'in-app notifications, daily email digests, or both. '
                'Go to Settings > Preferences > Notifications to customize.'
            ),
            entry_type='feature',
            release_date=date(2026, 1, 20),
            is_published=True,
            is_major=True,
            version='',
            learn_more_url='',
        )


def remove_release_note(apps, schema_editor):
    """Remove the Notification System release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(title='Notification System').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0047_notification_system'),
    ]

    operations = [
        migrations.RunPython(add_release_note, remove_release_note),
    ]
