# Manual migration: Rename Medicine → Intake, MedicineSchedule → IntakeSchedule,
# MedicineLog → IntakeLog. Also renames medicine_status → intake_status,
# FK fields (medicine → intake), and adds category + dosage_unit fields.
#
# Django's RenameModel handles:
# - Table rename (health_medicine → health_intake)
# - FK references on related models
# - ContentType updates
# - Existing indexes and constraints
#
# This migration is reversible.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0082_remove_creatine_drink_type_choice'),
    ]

    operations = [
        # Step 1: Rename models
        migrations.RenameModel(
            old_name='Medicine',
            new_name='Intake',
        ),
        migrations.RenameModel(
            old_name='MedicineSchedule',
            new_name='IntakeSchedule',
        ),
        migrations.RenameModel(
            old_name='MedicineLog',
            new_name='IntakeLog',
        ),

        # Step 2: Rename the status field
        migrations.RenameField(
            model_name='intake',
            old_name='medicine_status',
            new_name='intake_status',
        ),

        # Step 3: Rename FK fields
        migrations.RenameField(
            model_name='intakeschedule',
            old_name='medicine',
            new_name='intake',
        ),
        migrations.RenameField(
            model_name='intakelog',
            old_name='medicine',
            new_name='intake',
        ),

        # Step 4: Add new classification fields
        migrations.AddField(
            model_name='intake',
            name='category',
            field=models.CharField(
                choices=[
                    ('prescription', 'Prescription'),
                    ('otc', 'Over-the-Counter'),
                    ('vitamin', 'Vitamin'),
                    ('mineral', 'Mineral'),
                    ('amino_acid', 'Amino Acid'),
                    ('performance', 'Performance'),
                    ('hormonal', 'Hormonal'),
                    ('herbal', 'Herbal'),
                    ('probiotic', 'Probiotic'),
                    ('other', 'Other'),
                ],
                default='other',
                help_text='Finer classification (prescription, vitamin, amino_acid, etc.)',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='intake',
            name='dosage_unit',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Unit of measurement (mg, g, IU, mcg, ml)',
                max_length=20,
            ),
        ),

        # Step 5: Update Meta verbose names
        migrations.AlterModelOptions(
            name='intake',
            options={'ordering': ['name'], 'verbose_name': 'intake', 'verbose_name_plural': 'intake items'},
        ),
        migrations.AlterModelOptions(
            name='intakeschedule',
            options={'ordering': ['scheduled_time'], 'verbose_name': 'intake schedule', 'verbose_name_plural': 'intake schedules'},
        ),
        migrations.AlterModelOptions(
            name='intakelog',
            options={'ordering': ['-scheduled_date', '-scheduled_time'], 'verbose_name': 'intake log', 'verbose_name_plural': 'intake logs'},
        ),
    ]
