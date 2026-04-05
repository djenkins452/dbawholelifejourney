"""
Fix cycling workout that was incorrectly merged into a manual workout.

Previous migration (0075) targeted the wrong email. This one uses the correct one.
"""

from django.db import migrations


def fix_merged_cycling_sync_id(apps, schema_editor):
    WorkoutSession = apps.get_model("health", "WorkoutSession")
    User = apps.get_model("users", "User")

    try:
        user = User.objects.get(email="dannyjenkins71@gmail.com")
    except User.DoesNotExist:
        return

    from datetime import date

    target_date = date(2026, 4, 4)

    # Find manual workouts on that date that got a sync_id incorrectly
    # merged from a HealthKit cycling workout — clear it so the cycling
    # workout creates its own entry on next sync
    merged = WorkoutSession.objects.filter(
        user=user,
        date=target_date,
        source="manual",
        sync_id__gt="",
    )

    for workout in merged:
        workout.sync_id = ""
        workout.save(update_fields=["sync_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0075_fix_merged_cycling_sync_id"),
    ]

    operations = [
        migrations.RunPython(fix_merged_cycling_sync_id, migrations.RunPython.noop),
    ]
