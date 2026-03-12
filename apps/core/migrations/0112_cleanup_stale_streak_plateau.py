"""
Data migration: Clean up stale streak insights and plateau guidance items.

- Dismisses journal_streak_positive insights (user doesn't want streak language)
- Deactivates guidance items backed by plateau insights that were already dismissed
"""

from django.db import migrations


def cleanup_stale_items(apps, schema_editor):
    Insight = apps.get_model("core", "Insight")
    GuidanceItem = apps.get_model("core", "GuidanceItem")

    # 1. Dismiss all active streak insights
    streak_dismissed = Insight.objects.filter(
        insight_type="journal_streak_positive",
        status__in=["new", "read"],
    ).update(status="dismissed")

    # 2. Deactivate guidance items backed by plateau insights
    plateau_deactivated = GuidanceItem.objects.filter(
        guidance_type__in=["strength_plateau", "workout_frequency_adjustment"],
        is_active=True,
        dismissed_at__isnull=True,
    ).update(is_active=False)

    if streak_dismissed or plateau_deactivated:
        print(
            f"\n  Cleaned up: {streak_dismissed} streak insights dismissed, "
            f"{plateau_deactivated} plateau guidance items deactivated"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0111_add_threshold_budget_and_ratelimit_fields"),
    ]

    operations = [
        migrations.RunPython(cleanup_stale_items, migrations.RunPython.noop),
    ]
