"""Rename 'medicine' feature flag key to 'intake' in health_features JSON."""

from django.db import migrations


def rename_medicine_to_intake(apps, schema_editor):
    UserPreferences = apps.get_model("users", "UserPreferences")
    for prefs in UserPreferences.objects.exclude(health_features={}).exclude(
        health_features__isnull=True
    ):
        hf = prefs.health_features or {}
        if "medicine" in hf:
            hf["intake"] = hf.pop("medicine")
            prefs.health_features = hf
            prefs.save(update_fields=["health_features"])


def rename_intake_to_medicine(apps, schema_editor):
    UserPreferences = apps.get_model("users", "UserPreferences")
    for prefs in UserPreferences.objects.exclude(health_features={}).exclude(
        health_features__isnull=True
    ):
        hf = prefs.health_features or {}
        if "intake" in hf:
            hf["medicine"] = hf.pop("intake")
            prefs.health_features = hf
            prefs.save(update_fields=["health_features"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0082_userpreferences_assistant_assertiveness"),
    ]

    operations = [
        migrations.RunPython(rename_medicine_to_intake, rename_intake_to_medicine),
    ]
