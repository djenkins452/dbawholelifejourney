"""
Data migration: Purge stale fasting_fitness DomainCorrelation rows for users
who do NOT have fasting enabled.

Background: detect_fasting_fitness() previously defaulted missing
fasting_compliance_score to 0, which caused the engine to emit false
"Both fasting (0%) and workout consistency (X%) have dropped" correlations
for users who never fasted. The detector + state builder are now gated
properly, but stale correlations may already exist in production. This
migration deletes them so CoS does not surface them after the fix lands.

A user is considered "fasting disabled" when EITHER:
  - UserPreferences.health_features['fasting'] is explicitly False, OR
  - UserPreferences.default_fasting_type == 'none'
"""

from django.db import migrations


def purge_stale_fasting_correlations(apps, schema_editor):
    DomainCorrelation = apps.get_model("core", "DomainCorrelation")
    UserPreferences = apps.get_model("users", "UserPreferences")

    fasting_corr_qs = DomainCorrelation.objects.filter(
        correlation_type="fasting_fitness",
    )
    if not fasting_corr_qs.exists():
        return

    user_ids_with_fasting_corr = set(
        fasting_corr_qs.values_list("user_id", flat=True)
    )

    disabled_user_ids = set()
    prefs_qs = UserPreferences.objects.filter(
        user_id__in=user_ids_with_fasting_corr,
    ).values("user_id", "health_features", "default_fasting_type")

    for row in prefs_qs:
        health_features = row.get("health_features") or {}
        fasting_toggle = health_features.get("fasting", True)
        fasting_type = row.get("default_fasting_type") or "none"
        if (fasting_toggle is False) or (fasting_type == "none"):
            disabled_user_ids.add(row["user_id"])

    # Users with a fasting correlation but no UserPreferences row at all
    # are extreme edge cases — leave their correlations alone.

    if not disabled_user_ids:
        return

    deleted, _ = fasting_corr_qs.filter(user_id__in=disabled_user_ids).delete()
    if deleted:
        print(
            f"\n  Purged {deleted} stale fasting_fitness correlation(s) "
            f"for {len(disabled_user_ids)} user(s) with fasting disabled."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0122_add_execution_signal"),
    ]

    operations = [
        migrations.RunPython(
            purge_stale_fasting_correlations,
            migrations.RunPython.noop,
        ),
    ]
