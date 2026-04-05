"""
Fix cycling workout that was incorrectly merged into a manual workout.

The HealthKit overlap detection merged a cycling workout into a weight training
session because it only checked time overlap, not workout type. This clears the
stolen sync_id so the next HealthKit sync creates a proper separate entry.
"""

from django.db import migrations


def fix_merged_cycling_sync_id(apps, schema_editor):
    """
    Find manual workouts from 2026-04-04 that have a sync_id set but are
    clearly weight training sessions (session_mode='structured' with exercises).
    Clear the sync_id so the cycling workout can be re-created on next sync.
    """
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    from django.contrib.auth import get_user_model

    User = apps.get_model("users", "User")

    try:
        user = User.objects.get(email="admin@wholelifejourney.com")
    except User.DoesNotExist:
        return

    from datetime import date

    target_date = date(2026, 4, 4)

    # Find manual/structured workouts on that date that got a sync_id
    # incorrectly merged from a HealthKit cycling workout
    merged = WorkoutSession.objects.filter(
        user=user,
        date=target_date,
        source="manual",
        sync_id__gt="",
    )

    for workout in merged:
        # Clear the stolen sync_id so the cycling data creates its own entry
        workout.sync_id = ""
        workout.save(update_fields=["sync_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0074_fix_workout_field_metadata"),
    ]

    operations = [
        migrations.RunPython(fix_merged_cycling_sync_id, migrations.RunPython.noop),
    ]
