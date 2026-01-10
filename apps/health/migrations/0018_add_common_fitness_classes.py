# Generated manually - adds common fitness class exercises

from django.db import migrations


def add_fitness_classes(apps, schema_editor):
    """Add common fitness class exercises."""
    Exercise = apps.get_model('health', 'Exercise')

    classes = [
        'Orange Theory',
        'F45 Training',
        'CrossFit',
        'Yoga Class',
        'Hot Yoga',
        'Spin Class',
        'Pilates',
        'HIIT Class',
        'Boot Camp',
        'Zumba',
        'Barre Class',
        'Boxing Class',
        'Kickboxing',
        'Dance Fitness',
        'Aqua Aerobics',
        'Circuit Training',
        'TRX Class',
        'Strength & Conditioning',
    ]

    for name in classes:
        Exercise.objects.get_or_create(
            name=name,
            category='class',
            defaults={'is_active': True}
        )


def remove_fitness_classes(apps, schema_editor):
    """Remove the fitness classes (for rollback)."""
    Exercise = apps.get_model('health', 'Exercise')
    Exercise.objects.filter(category='class').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0017_add_fitness_class_category_and_details'),
    ]

    operations = [
        migrations.RunPython(add_fitness_classes, remove_fitness_classes),
    ]
