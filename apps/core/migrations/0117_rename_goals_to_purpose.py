"""
Data migration: rename module="goals" → "purpose" in Insight, Prediction, and
GuidanceItem records.

The goals domain was standardized to "purpose" in the Phase 2 signal emitter
audit (2026-03-16). Historical records still have the old name, causing
compute_signal_health() to report a ghost "goals" domain in signal drought.

Runs automatically on deploy via Procfile: python manage.py migrate --noinput.
"""

from django.db import migrations


def rename_goals_to_purpose(apps, schema_editor):
    """Rename module='goals' → 'purpose' in Insight, Prediction, and GuidanceItem records."""
    Insight = apps.get_model("core", "Insight")
    updated_insights = Insight.objects.filter(module="goals").update(module="purpose")

    Prediction = apps.get_model("core", "Prediction")
    updated_predictions = Prediction.objects.filter(module="goals").update(module="purpose")

    GuidanceItem = apps.get_model("core", "GuidanceItem")
    updated_guidance = GuidanceItem.objects.filter(module="goals").update(module="purpose")

    if updated_insights or updated_predictions or updated_guidance:
        print(
            f"\n  Renamed module 'goals' → 'purpose': "
            f"{updated_insights} insights, {updated_predictions} predictions, "
            f"{updated_guidance} guidance items"
        )


def noop(apps, schema_editor):
    """Reverse is a no-op — the old name is not needed."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0116_add_validator_metric_and_spike_type"),
    ]

    operations = [
        migrations.RunPython(rename_goals_to_purpose, noop),
    ]
