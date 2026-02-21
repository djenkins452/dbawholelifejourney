"""
Remove dummy sleep entries created by heart rate sync.

The heart rate processor used to create fake 8-hour sleep entries
(total_duration_minutes=480, bedtime=10PM, wake_time=6AM) when no
real sleep entry existed for a date. This migration deletes those
dummy entries so only real sleep data remains.
"""

from django.db import migrations


def remove_dummy_sleep_entries(apps, schema_editor):
    """Delete sleep entries that were created as HR-only containers."""
    SleepEntry = apps.get_model("health", "SleepEntry")

    # Dummy entries have exactly 480 minutes, no stage data, no quality,
    # and come from apple_health source
    dummy_entries = SleepEntry.objects.filter(
        source="apple_health",
        total_duration_minutes=480,
        asleep_duration_minutes__isnull=True,
        stage_deep_minutes__isnull=True,
        stage_rem_minutes__isnull=True,
        stage_light_minutes__isnull=True,
        stage_awake_minutes__isnull=True,
        quality_rating="",
        quality_score__isnull=True,
    )

    count = dummy_entries.count()
    # Hard delete — these are fake data, not user-created
    dummy_entries.delete()

    if count:
        print(f"\n  Removed {count} dummy sleep entries created by heart rate sync.")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0047_add_mobility_hr_events_audio_dietary_models"),
    ]

    operations = [
        migrations.RunPython(remove_dummy_sleep_entries, noop),
    ]
