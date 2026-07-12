# ==============================================================================
# Data migration: decontaminate the Weight truth domain.
#
# Incident (2026-07-12): body measurements (chest/waist/hips, unit "in") were written
# into WeightEntry via a fail-open log_weight path. Because every weight reader (Weight
# page, SAE weight_current, dashboard, Body Intelligence, CoS) reads the latest
# WeightEntry, this produced impossible values ("51.0 in latest weight", "-198.6 lb").
#
# This migration RESTORES the Weight domain deterministically and PRESERVES the user's
# data (never destroys it):
#   1. Find every ACTIVE WeightEntry whose unit is not a real weight unit (lb/kg).
#   2. Re-home it as a BodyCompositionEntry (metric inferred from its notes; "custom"
#      when unknown), which is its correct domain — nothing is lost.
#   3. Soft-delete the offending WeightEntry (status="deleted") so it leaves the Weight
#      pipeline while remaining recoverable.
#
# Idempotent and safe on clean databases (no offending rows → no-op). The model-level
# guard added in the same change makes new contamination structurally impossible.
# ==============================================================================
from django.db import migrations
from django.utils import timezone


# notes-keyword → canonical body-composition metric_name.
_NOTES_TO_METRIC = [
    ("chest", "chest"),
    ("waist", "waist"),
    ("hip", "hips"),
    ("neck", "neck"),
    ("shoulder", "shoulders"),
    ("forearm", "forearm_right"),
    ("bicep", "arm_right"),   # canonical WLJ name is arm_*, never "bicep"
    ("arm", "arm_right"),
    ("thigh", "thigh_right"),
    ("calf", "calf_right"),
    ("body fat", "body_fat_pct"),
    ("lean", "lean_mass"),
    ("fat mass", "fat_mass"),
    ("skeletal", "skeletal_muscle_mass"),
    ("visceral", "visceral_fat"),
    ("water", "body_water_pct"),
    ("bone", "bone_mass"),
    ("bmi", "bmi"),
    ("bmr", "bmr"),
]

_WEIGHT_UNITS = ("lb", "kg")


def _infer_metric(notes):
    text = (notes or "").lower()
    for keyword, metric in _NOTES_TO_METRIC:
        if keyword in text:
            return metric
    return None


def decontaminate(apps, schema_editor):
    WeightEntry = apps.get_model("health", "WeightEntry")
    BodyCompositionEntry = apps.get_model("health", "BodyCompositionEntry")

    now = timezone.now()
    # Only touch ACTIVE rows with a non-weight unit — those are the contaminants.
    offenders = WeightEntry.objects.filter(status="active").exclude(unit__in=_WEIGHT_UNITS)

    moved = 0
    for we in offenders.iterator():
        metric = _infer_metric(we.notes) or "custom"
        measurement_date = we.recorded_at.date()

        # Preserve the datum as a BodyCompositionEntry (its correct domain), avoiding a
        # duplicate if an identical measurement already exists.
        exists = BodyCompositionEntry.objects.filter(
            user_id=we.user_id,
            metric_name=metric,
            measurement_date=measurement_date,
            value=we.value,
        ).exists()
        if not exists:
            BodyCompositionEntry.objects.create(
                user_id=we.user_id,
                metric_name=metric,
                value=we.value,
                unit=(we.unit or "in"),
                measurement_date=measurement_date,
                source=(we.source or "manual"),
                notes=we.notes or "",
                created_via=getattr(we, "created_via", "manual") or "manual",
                status="active",
            )

        # Remove the offending row from the Weight domain (reversible soft delete).
        we.status = "deleted"
        we.deleted_at = now
        we.save(update_fields=["status", "deleted_at", "updated_at"])
        moved += 1

    if moved:
        print(f"  [decontaminate_weight] re-homed + soft-deleted {moved} non-weight WeightEntry row(s)")


def noop_reverse(apps, schema_editor):
    # Deliberately irreversible: we never re-contaminate the Weight domain.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0099_bodymeasurementsession_and_more"),
    ]

    operations = [
        migrations.RunPython(decontaminate, noop_reverse),
    ]
