# ==============================================================================
# Data migration: correct FoodEntry rows whose nutrition was DOUBLE-SCALED by quantity.
#
# Defect (fixed in code this same change): the client wrote the scaled line total back into
# the per-serving nutrient fields and the form multiplied by quantity again, so a food logged
# with quantity N stored per_serving × N as its "per-serving" snapshot and per_serving × N²
# as its line total (qty 2 -> 4× calories).
#
# This migration corrects ONLY rows where the corruption is DETERMINISTICALLY PROVABLE against
# the food's own catalog record: the stored snapshot matches (catalog per-serving × quantity)
# but NOT (catalog per-serving). For those, the true per-serving is recovered from the stored
# snapshot ÷ quantity (log-time accurate, no catalog-drift dependency) and the line total is
# recomputed as per_serving × quantity. Every other row — correct rows, quantity == 1, and
# source-less rows we cannot verify — is left UNTOUCHED and only counted. Idempotent.
# ==============================================================================
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

# snapshot key -> FoodEntry line-total field
KEY_TO_TOTAL = {
    "calories": "total_calories",
    "protein_g": "total_protein_g",
    "carbohydrates_g": "total_carbohydrates_g",
    "fiber_g": "total_fiber_g",
    "sugar_g": "total_sugar_g",
    "fat_g": "total_fat_g",
    "saturated_fat_g": "total_saturated_fat_g",
    "sodium_mg": "total_sodium_mg",
    "cholesterol_mg": "total_cholesterol_mg",
    "potassium_mg": "total_potassium_mg",
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _close(a, b, tol=0.02):
    """a within tol (relative) of b."""
    if a is None or b is None:
        return False
    return abs(a - b) <= tol * max(abs(b), 1.0)


def fix_double_scaling(apps, schema_editor):
    FoodEntry = apps.get_model("health", "FoodEntry")

    fixed = source_less = catalog_missing = already_correct = undetectable = 0
    qs = FoodEntry.objects.exclude(quantity=1).exclude(quantity__isnull=True)

    for entry in qs.iterator():
        try:
            qty = _f(entry.quantity)
            snap = entry.snapshot_nutrients or {}
            stored_cal = _f(snap.get("calories"))
            if not qty or qty == 1 or stored_cal is None:
                undetectable += 1
                continue

            source = getattr(entry, "food_item", None) or getattr(entry, "custom_food", None)
            if source is None:
                source_less += 1              # cannot verify — leave untouched
                continue
            catalog_cal = _f(getattr(source, "calories", None))
            if not catalog_cal:
                catalog_missing += 1
                continue

            # PROVABLE double-scale: snapshot ≈ catalog×qty and NOT ≈ catalog.
            if _close(stored_cal, catalog_cal * qty) and not _close(stored_cal, catalog_cal):
                # Recover per-serving from the stored (log-time) snapshot ÷ qty; recompute
                # the line total as per_serving × qty = the OLD snapshot value (correct total).
                corrected_snap = {}
                for k, v in snap.items():
                    fv = _f(v)
                    corrected_snap[k] = round(fv / qty, 4) if fv is not None else v
                update_fields = ["snapshot_nutrients"]
                entry.snapshot_nutrients = corrected_snap
                for k, tot_field in KEY_TO_TOTAL.items():
                    if k in corrected_snap and _f(corrected_snap[k]) is not None:
                        setattr(entry, tot_field, round(_f(corrected_snap[k]) * qty, 2))
                        update_fields.append(tot_field)
                entry.save(update_fields=update_fields)
                fixed += 1
            else:
                already_correct += 1
        except Exception:  # never let one bad row abort the migration
            logger.warning("fix_double_scaling: skipped entry id=%s",
                           getattr(entry, "id", "?"), exc_info=True)
            undetectable += 1

    logger.warning(
        "NUTRITION DOUBLE-SCALE MIGRATION: fixed=%s (provably double-scaled, source-backed) | "
        "already_correct=%s | source_less_qty_not_1=%s (UNTOUCHED — cannot verify) | "
        "catalog_missing=%s | undetectable=%s",
        fixed, already_correct, source_less, catalog_missing, undetectable)


def noop_reverse(apps, schema_editor):
    # Data correction is not reversible (originals were already corrupt); safe no-op.
    pass


class Migration(migrations.Migration):
    dependencies = [("health", "0105_fix_future_dated_heart_rate_recorded_at")]
    operations = [migrations.RunPython(fix_double_scaling, noop_reverse)]
