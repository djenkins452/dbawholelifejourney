"""
Data migration: Convert legacy commitment_level values to new importance tiers.

Mapping:
    non_negotiable → foundational
    optional → flexible
    important → important (unchanged)

Also converts CalendarEvent, LifeGoal, HabitGoal, GovernanceProfile records.
"""
from django.db import migrations


def convert_commitment_values(apps, schema_editor):
    """Convert old commitment_level values to new importance tiers across all models."""
    mapping = {
        'non_negotiable': 'foundational',
        'optional': 'flexible',
    }

    models_to_update = [
        ('life', 'Task'),
        ('purpose', 'LifeGoal'),
        ('purpose', 'HabitGoal'),
        ('calendar_engine', 'CalendarEvent'),
        ('core', 'GovernanceProfile'),
    ]

    total_updated = 0
    for app_label, model_name in models_to_update:
        try:
            Model = apps.get_model(app_label, model_name)
            for old_val, new_val in mapping.items():
                count = Model.objects.filter(commitment_level=old_val).update(
                    commitment_level=new_val
                )
                if count:
                    total_updated += count
                    print(f"  {model_name}: {count} records {old_val} → {new_val}")
        except Exception as e:
            print(f"  {model_name}: skipped ({e})")

    if total_updated:
        print(f"  Total: {total_updated} records normalized")


def reverse_noop(apps, schema_editor):
    pass  # Cannot reliably reverse — old values are ambiguous


class Migration(migrations.Migration):
    dependencies = [
        ('life', '0037_normalize_commitment_to_importance'),
        ('purpose', '0011_normalize_commitment_to_importance'),
        ('calendar_engine', '0010_normalize_commitment_to_importance'),
        ('core', '0119_normalize_commitment_to_importance'),
    ]

    operations = [
        migrations.RunPython(convert_commitment_values, reverse_noop),
    ]
