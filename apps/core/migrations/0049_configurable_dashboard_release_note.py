# Generated manually for configurable dashboard release note

from django.db import migrations
from django.utils import timezone


def create_release_note(apps, schema_editor):
    """Create release note for configurable dashboard feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if already exists
    if ReleaseNote.objects.filter(version='2026.01.20-dashboard').exists():
        return

    ReleaseNote.objects.create(
        version='2026.01.20-dashboard',
        title='Customizable Dashboard',
        description=(
            'Your dashboard, your way! You can now:\n\n'
            '- Drag and drop tiles to rearrange them\n'
            '- Show or hide sections you don\'t use\n'
            '- Choose small, medium, or large sizes for each tile\n\n'
            'Look for the "Customize Your Dashboard" banner on your dashboard, '
            'or visit Dashboard - Customize anytime to adjust your layout.'
        ),
        entry_type='feature',
        release_date=timezone.now().date(),
        is_published=True,
        is_major=True,
    )


def reverse_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(version='2026.01.20-dashboard').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0048_notification_system_release_note'),
    ]

    operations = [
        migrations.RunPython(create_release_note, reverse_release_note),
    ]
