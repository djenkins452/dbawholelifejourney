# ==============================================================================
# File: apps/health/migrations/0110_seed_usda_generic_foods.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: One-time seed of the USDA generic food catalog on deploy
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-08
# ==============================================================================
"""Seed the generic food catalog, because production has no shell to run a command in.

`FoodItem` was never a catalog — an opportunistic cache of past lookups, 1,585 AI estimates
and 31 barcode scans in production, zero generic foods. Ranking cannot fix that: ordering
nothing produces nothing. The importer shipped, and there was no way to run it.

So the trimmed SR Legacy extract rides with the app and seeds itself here, once. It is
guarded on the catalog being empty of USDA rows, so a redeploy costs one COUNT query rather
than 7,793 upserts, and a later refresh is the management command's job — which updates in
place and is what should carry a newer USDA release.

Reversing drops ONLY the rows this seeded (`data_source='usda'`). FatSecret, barcode and
user-created rows are never touched.
"""

from django.db import migrations

_BATCH = 1000


def _is_test_database(schema_editor):
    """A seed migration must not redefine the baseline of every unrelated test.

    7,793 catalog rows in each test database slows every run and silently couples suites
    that know nothing about food to the contents of a USDA release — several did object
    the first time this ran. Tests that need the catalog seed it explicitly with the
    management command, which is also what production refreshes with.
    """
    name = str((schema_editor.connection.settings_dict or {}).get("NAME") or "")
    return name.startswith("test_") or "/test_" in name


def seed(apps, schema_editor):
    if _is_test_database(schema_editor):
        return

    from apps.health.management.commands.import_usda_foods import (
        BUNDLED_SOURCE, _NUTRIENTS, _SERVING_SIZE, _SERVING_UNIT, iter_foods, load_source,
    )

    FoodItem = apps.get_model("health", "FoodItem")
    if FoodItem.objects.filter(data_source="usda").exists():
        return  # already seeded; refresh is the command's job

    try:
        payload = load_source(BUNDLED_SOURCE)
    except OSError:
        return  # the extract is absent (slim checkout); the command can still seed later

    rows = []
    for food in iter_foods(payload):
        fdc_id, name = food.get("fdcId"), (food.get("description") or "").strip()
        if not fdc_id or not name:
            continue
        nutrients = {}
        for entry in (food.get("foodNutrients") or []):
            field = _NUTRIENTS.get((entry.get("nutrient") or {}).get("id"))
            amount = entry.get("amount")
            if field and amount is not None:
                nutrients[field] = amount
        if "calories" not in nutrients:
            continue
        rows.append(FoodItem(
            name=name[:300], data_source="usda", source_reference=str(fdc_id),
            serving_size=_SERVING_SIZE, serving_unit=_SERVING_UNIT,
            is_active=True, is_verified=True,
            external_ids={"usda_fdb_id": str(fdc_id)}, **nutrients))

    FoodItem.objects.bulk_create(rows, batch_size=_BATCH, ignore_conflicts=True)


def unseed(apps, schema_editor):
    apps.get_model("health", "FoodItem").objects.filter(data_source="usda").delete()


class Migration(migrations.Migration):
    dependencies = [("health", "0109_food_entry_nutrition_unknown_source")]
    operations = [migrations.RunPython(seed, unseed)]
