"""
Phase 4: Create default PressureWeightConfig record.

Weights: density=30, compression=20, breach=20, erosion=15, collision=15.
"""

from django.db import migrations


def create_default_weight_config(apps, schema_editor):
    PressureWeightConfig = apps.get_model('core', 'PressureWeightConfig')
    if not PressureWeightConfig.objects.filter(active=True).exists():
        PressureWeightConfig.objects.create(
            density_weight=30,
            compression_weight=20,
            breach_weight=20,
            erosion_weight=15,
            collision_weight=15,
            active=True,
        )


def reverse_default_weight_config(apps, schema_editor):
    PressureWeightConfig = apps.get_model('core', 'PressureWeightConfig')
    PressureWeightConfig.objects.filter(active=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0091_phase4_pressure_models'),
    ]

    operations = [
        migrations.RunPython(
            create_default_weight_config,
            reverse_default_weight_config,
        ),
    ]
