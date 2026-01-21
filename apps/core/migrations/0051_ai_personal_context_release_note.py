# Generated manually for AI Personal Context Memory release note

from django.db import migrations
from django.utils import timezone


def create_release_note(apps, schema_editor):
    """Create release note for AI Personal Context Memory feature."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')

    # Check if already exists
    if ReleaseNote.objects.filter(version='2026.01.20-memory').exists():
        return

    ReleaseNote.objects.create(
        version='2026.01.20-memory',
        title='AI Now Remembers You',
        description=(
            'Your AI assistant now learns and remembers personal facts from your conversations '
            'to provide more empathetic, personalized responses.\n\n'
            'For example, if you share that your parents divorced when you were young, '
            'the AI will be more thoughtful when discussing family topics.\n\n'
            'You have full control:\n'
            '- Say "don\'t save that" during a conversation to prevent saving\n'
            '- View and edit what the AI knows in Settings > What I Know About You\n'
            '- Clear everything with one click\n\n'
            'Your data is encrypted and never shared.'
        ),
        entry_type='feature',
        release_date=timezone.now().date(),
        is_published=True,
        is_major=False,
    )


def reverse_release_note(apps, schema_editor):
    """Remove the release note."""
    ReleaseNote = apps.get_model('core', 'ReleaseNote')
    ReleaseNote.objects.filter(version='2026.01.20-memory').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0050_daniel_reading_plan_release_note'),
    ]

    operations = [
        migrations.RunPython(create_release_note, reverse_release_note),
    ]
