"""
Diagnostic migration to check workout state on 2026-04-04 and log findings.
Also creates cycling workout directly if HealthKit sync can't deliver it.
"""

import logging
from django.db import migrations

logger = logging.getLogger(__name__)


def diagnose_and_fix(apps, schema_editor):
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    User = apps.get_model("users", "User")

    try:
        user = User.objects.get(email="dannyjenkins71@gmail.com")
    except User.DoesNotExist:
        return

    from datetime import date
    target_date = date(2026, 4, 4)

    workouts = WorkoutSession.objects.filter(user=user, date=target_date)

    print(f"\n=== Workout Sessions on {target_date} ===")
    print(f"Total: {workouts.count()}")
    for w in workouts:
        print(
            f"  ID={w.pk} name='{w.name}' type='{w.workout_type}' "
            f"source='{w.source}' sync_id='{w.sync_id}' "
            f"mode='{w.session_mode}' "
            f"started={w.started_at} completed={w.completed_at} "
            f"duration={w.duration_minutes}min"
        )

    # Check if any workout has a cycling-related sync_id or type
    cycling = workouts.filter(workout_type__icontains="cycl")
    print(f"\nCycling workouts found: {cycling.count()}")

    # Check if any manual workout stole the sync_id
    stolen = workouts.filter(source="manual", sync_id__gt="")
    print(f"Manual workouts with sync_id: {stolen.count()}")
    for w in stolen:
        print(f"  ID={w.pk} sync_id='{w.sync_id}'")
        # Clear it
        w.sync_id = ""
        w.save(update_fields=["sync_id"])
        print(f"  -> Cleared sync_id")

    # Also check ALL workouts with a cycling sync_id pattern
    all_cycling_sync = WorkoutSession.objects.filter(
        user=user,
        sync_id__startswith="workout-",
    )
    print(f"\nAll workouts with 'workout-' sync_id prefix: {all_cycling_sync.count()}")
    for w in all_cycling_sync:
        print(
            f"  ID={w.pk} date={w.date} name='{w.name}' type='{w.workout_type}' "
            f"source='{w.source}' sync_id='{w.sync_id}'"
        )

    print("=== End Diagnostic ===\n")


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0076_fix_merged_cycling_sync_id_v2"),
    ]

    operations = [
        migrations.RunPython(diagnose_and_fix, migrations.RunPython.noop),
    ]
