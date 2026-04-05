# Generated manually for the Unified Intake System migration.
# Seeds a Creatine supplement entry for users with active creatine hydration history.

from datetime import time

from django.db import migrations


def seed_creatine_supplements(apps, schema_editor):
    """
    For users who have WaterEntry records with drink_type='creatine',
    create a Medicine entry (intake_type='supplement') so they can
    continue tracking creatine through the structured intake system.

    Only creates if the user does NOT already have an active creatine Medicine.
    """
    WaterEntry = apps.get_model('health', 'WaterEntry')
    Medicine = apps.get_model('health', 'Medicine')
    MedicineSchedule = apps.get_model('health', 'MedicineSchedule')

    # Find users with creatine water entries
    user_ids = (
        WaterEntry.objects
        .filter(drink_type='creatine')
        .values_list('user_id', flat=True)
        .distinct()
    )

    for user_id in user_ids:
        # Skip if user already has a creatine medicine/supplement
        existing = Medicine.objects.filter(
            user_id=user_id,
            name__icontains='creatine',
        ).exclude(medicine_status='completed').exists()
        if existing:
            continue

        # Get earliest creatine log date for start_date
        first_log = (
            WaterEntry.objects
            .filter(user_id=user_id, drink_type='creatine')
            .order_by('logged_date')
            .values_list('logged_date', flat=True)
            .first()
        )
        if not first_log:
            continue

        # Create the supplement
        med = Medicine.objects.create(
            user_id=user_id,
            name='Creatine',
            purpose='Muscle recovery and performance',
            dose='5g',
            frequency='daily',
            is_prn=False,
            start_date=first_log,
            medicine_status='active',
            intake_type='supplement',
            priority='optimization',
            grace_period_minutes=120,
            instructions='Mix with water. Take daily for consistency.',
            notes='Auto-seeded from hydration tracking history.',
        )

        # Create a morning schedule
        MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=time(7, 0),
            time_of_day='morning',
            label='Morning creatine',
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )


def reverse_seed(apps, schema_editor):
    """Remove auto-seeded creatine supplements."""
    Medicine = apps.get_model('health', 'Medicine')
    Medicine.objects.filter(
        intake_type='supplement',
        name='Creatine',
        notes='Auto-seeded from hydration tracking history.',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('health', '0080_unified_intake_system_fields'),
    ]

    operations = [
        migrations.RunPython(seed_creatine_supplements, reverse_seed),
    ]
