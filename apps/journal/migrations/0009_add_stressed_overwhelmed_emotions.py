# Generated data migration — add Stressed and Overwhelmed emotions

from django.db import migrations


def add_emotions(apps, schema_editor):
    """Add Stressed and Overwhelmed to the Emotion model."""
    Emotion = apps.get_model('journal', 'Emotion')

    new_emotions = [
        {'name': 'Stressed', 'slug': 'stressed', 'emoji': '😣', 'order': 15},
        {'name': 'Overwhelmed', 'slug': 'overwhelmed', 'emoji': '😵', 'order': 16},
    ]

    for data in new_emotions:
        Emotion.objects.get_or_create(
            slug=data['slug'],
            defaults={
                'name': data['name'],
                'emoji': data['emoji'],
                'order': data['order'],
                'is_active': True,
            },
        )


def remove_emotions(apps, schema_editor):
    """Remove Stressed and Overwhelmed emotions."""
    Emotion = apps.get_model('journal', 'Emotion')
    Emotion.objects.filter(slug__in=['stressed', 'overwhelmed']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0008_backfill_journal_signals'),
    ]

    operations = [
        migrations.RunPython(add_emotions, remove_emotions),
    ]
