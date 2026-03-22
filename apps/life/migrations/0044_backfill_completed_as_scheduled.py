"""
Backfill completed_as_scheduled for existing RoutineLogs.

- log_status='completed' → completed_as_scheduled=True (on-time)
- log_status='completed_late' → completed_as_scheduled=False (late)
"""

from django.db import migrations


def backfill(apps, schema_editor):
    RoutineLog = apps.get_model('life', 'RoutineLog')
    updated = RoutineLog.objects.filter(
        log_status='completed',
        completed_as_scheduled=False,
    ).update(completed_as_scheduled=True)
    if updated:
        print(f"  Backfilled {updated} completed logs → completed_as_scheduled=True")


def reverse_backfill(apps, schema_editor):
    RoutineLog = apps.get_model('life', 'RoutineLog')
    RoutineLog.objects.all().update(completed_as_scheduled=False)


class Migration(migrations.Migration):
    dependencies = [
        ('life', '0043_routinelog_completed_as_scheduled'),
    ]

    operations = [
        migrations.RunPython(backfill, reverse_backfill),
    ]
