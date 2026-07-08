# ==============================================================================
# Data migration: collapse legacy dual-defined routines onto the canonical
# RoutineSchedule (commit 2 of single-source execution). Runs the tested service
# `routine_cleanup.collapse_dual_defined_routines`. Depends on calendar_engine so the
# CalendarEvent table exists when this runs on a fresh build (cross-app data-migration
# rule) — the service also guards CalendarEvent access defensively. Idempotent; reverse
# is a no-op (soft-deleted twins are not resurrected).
# ==============================================================================
from django.db import migrations


def collapse(apps, schema_editor):
    # Use the real service (not the historical apps registry) — it needs model methods
    # (soft_delete, applies_to_day) and cross-app helpers the frozen models don't carry.
    from apps.life.services.routine_cleanup import collapse_dual_defined_routines
    collapse_dual_defined_routines()


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('life', '0055_backfill_routine_activity_types'),
        ('calendar_engine', '0013_backfill_missing_projections'),
    ]

    operations = [
        migrations.RunPython(collapse, noop),
    ]
