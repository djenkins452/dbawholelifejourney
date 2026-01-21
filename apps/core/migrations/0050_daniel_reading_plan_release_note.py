# Generated manually for Daniel reading plan release note

from django.db import migrations
from django.utils import timezone


def create_release_note(apps, schema_editor):
    """Create release note for Daniel reading plan."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if already exists
    if ReleaseNote.objects.filter(version='2026.01.21-daniel').exists():
        return

    ReleaseNote.objects.create(
        version='2026.01.21-daniel',
        title='New Character Study: Daniel',
        description=(
            'Explore Daniel: Faith in Exile - a 12-day journey through the Book of Daniel.\n\n'
            'Study Daniel\'s faithfulness in Babylon, the fiery furnace, the lions\' den, '
            'and prophetic visions including the four beasts, seventy weeks, and spiritual warfare.\n\n'
            'Available in Beginner, Intermediate, and Advanced levels. '
            'Find it under Faith > Reading Plans.'
        ),
        entry_type='feature',
        release_date=timezone.now().date(),
        is_published=True,
        is_major=False,
    )


def reverse_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(version='2026.01.21-daniel').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0049_configurable_dashboard_release_note'),
    ]

    operations = [
        migrations.RunPython(create_release_note, reverse_release_note),
    ]
