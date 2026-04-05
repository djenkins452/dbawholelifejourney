# Backfill category values for existing intake items.
# Medications default to 'prescription', creatine to 'amino_acid'.

from django.db import migrations


def backfill_categories(apps, schema_editor):
    Intake = apps.get_model('health', 'Intake')

    # All existing medications → prescription category
    Intake.objects.filter(
        intake_type='medication',
        category='other',
    ).update(category='prescription')

    # Creatine supplements → amino_acid category
    Intake.objects.filter(
        intake_type='supplement',
        name__icontains='creatine',
        category='other',
    ).update(category='amino_acid')


def reverse_backfill(apps, schema_editor):
    Intake = apps.get_model('health', 'Intake')
    Intake.objects.filter(category__in=['prescription', 'amino_acid']).update(category='other')


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0083_rename_medicine_to_intake'),
    ]

    operations = [
        migrations.RunPython(backfill_categories, reverse_backfill),
    ]
