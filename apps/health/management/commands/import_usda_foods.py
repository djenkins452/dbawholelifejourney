# ==============================================================================
# File: apps/health/management/commands/import_usda_foods.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Seed generic/base foods from USDA FoodData Central into FoodItem
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-06
# ==============================================================================
"""WLJ has never had a generic food catalog. This is the smallest one that scales.

`FoodItem` was documented as a "global food library" but written only by FatSecret
cache-back, AI estimates and barcode scans — an opportunistic cache of whatever anyone
happened to look up, which `load_initial_data` then periodically deletes. So a search for
an ordinary food had nothing to find, and on 2026-09-06 a plain banana was unavailable to
both the Nutrition UI and the Chief of Staff.

The source model this fills in:

    USDA FoodData Central  →  generic / base foods      (this command)
    FatSecret              →  restaurant and commercial
    Open Food Facts        →  branded / barcode
    CustomFood             →  the person's own saved foods

All four already feed the SAME `food_search_service` and the same deterministic ranking, so
seeding here needs no new search path and no new ranking rule.

WHAT IS IMPORTED — the generic datasets only: **SR Legacy** and **Foundation Foods**
(~10k rows, the base ingredients: "Bananas, raw"). NOT Branded Foods (~1.9M rows), which
is FatSecret's and Open Food Facts' territory and would dwarf the database for no gain.

WHAT IS NOT BUNDLED — the dataset itself. It is downloaded by the operator from
https://fdc.nal.usda.gov/download-datasets.html and passed in with `--source`. Committing a
30MB nutrition file to the repository would tie catalog refresh to a deploy.

    python manage.py import_usda_foods --source FoodData_Central_sr_legacy_food_json.json
    python manage.py import_usda_foods --source … --limit 500 --dry-run

IDEMPOTENT: a row is keyed by its FDC id (`data_source='usda'` + `source_reference`), so
re-running updates in place and never duplicates. Safe to run on every refresh.

REFRESH: USDA publishes roughly twice a year (April/October). Re-run with the new file;
existing rows update, new foods are added, and nothing else in the catalog is touched —
FatSecret, barcode and user-created rows are never read or written by this command.
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# USDA nutrient ids. These are the dataset's own stable identifiers, not a food list.
_NUTRIENTS = {
    1008: "calories",            # Energy (kcal)
    1003: "protein_g",           # Protein
    1005: "carbohydrates_g",     # Carbohydrate, by difference
    1004: "fat_g",               # Total lipid (fat)
    1079: "fiber_g",             # Fiber, total dietary
    2000: "sugar_g",             # Total sugars
    1258: "saturated_fat_g",     # Fatty acids, total saturated
}

# USDA generic entries are per 100 g. Recording that plainly is what keeps a serving
# honest; nothing here guesses a household portion.
_SERVING_SIZE = 100
_SERVING_UNIT = "g"

_BATCH = 500


def _nutrient_map(food):
    """Pull the handful of nutrients WLJ stores out of one USDA food record."""
    out = {}
    for entry in (food.get("foodNutrients") or []):
        nutrient = entry.get("nutrient") or {}
        field = _NUTRIENTS.get(nutrient.get("id"))
        if not field:
            continue
        amount = entry.get("amount")
        if amount is None:
            continue
        try:
            out[field] = round(float(amount), 2)
        except (TypeError, ValueError):
            continue
    return out


def _iter_foods(payload):
    """USDA ships either a bare list or a single-keyed object; accept both."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


class Command(BaseCommand):
    help = "Import USDA FoodData Central generic foods into the FoodItem catalog."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True,
                            help="Path to a USDA FoodData Central JSON export "
                                 "(SR Legacy or Foundation Foods).")
        parser.add_argument("--limit", type=int, default=0,
                            help="Import at most N foods (0 = all).")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would change without writing.")

    def handle(self, *args, **opts):
        from apps.health.models import FoodItem

        try:
            with open(opts["source"], "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except OSError as exc:
            raise CommandError(f"Could not read --source: {exc}")
        except json.JSONDecodeError as exc:
            raise CommandError(f"--source is not valid JSON: {exc}")

        foods = _iter_foods(payload)
        if not foods:
            raise CommandError("No foods found in --source. Expected a USDA JSON export.")

        limit = opts["limit"] or len(foods)
        created = updated = skipped = 0

        for start in range(0, min(limit, len(foods)), _BATCH):
            chunk = foods[start:min(start + _BATCH, limit)]
            with transaction.atomic():
                for food in chunk:
                    fdc_id = food.get("fdcId")
                    name = (food.get("description") or "").strip()
                    if not fdc_id or not name:
                        skipped += 1
                        continue
                    nutrients = _nutrient_map(food)
                    if "calories" not in nutrients:
                        # A food with no energy value cannot answer the question people
                        # actually ask of this catalog.
                        skipped += 1
                        continue
                    if opts["dry_run"]:
                        created += 1
                        continue
                    _, was_created = FoodItem.objects.update_or_create(
                        data_source=FoodItem.SOURCE_USDA,
                        source_reference=str(fdc_id),
                        defaults={
                            "name": name[:300],
                            "serving_size": _SERVING_SIZE,
                            "serving_unit": _SERVING_UNIT,
                            "is_active": True,
                            "is_verified": True,
                            "external_ids": {"usda_fdb_id": str(fdc_id)},
                            **nutrients,
                        },
                    )
                    created += int(was_created)
                    updated += int(not was_created)

        verb = "would import" if opts["dry_run"] else "imported"
        self.stdout.write(
            f"USDA catalog: {verb} {created} new, {updated} updated, {skipped} skipped "
            f"(source={opts['source']})")
