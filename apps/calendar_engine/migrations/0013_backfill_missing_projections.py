"""
Data migration: backfill CalendarEvent projection rows for source types that
have working projection code + wired signals but were never populated —
medicine/supplement schedules, workout schedules, faith reading plans, and
life events.

Their pre-existing objects (created before the signals existed, or via bulk
paths that skip post_save) have no CalendarEvent rows, so the calendar showed
almost nothing. This runs on deploy (the Procfile runs `migrate`) and re-derives
the rows from the SOURCE OBJECTS ONLY, via the same upsert functions the signals
use. Idempotent (upserts reuse existing rows) and fully guarded so it can never
fail a deploy.
"""

import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def forwards(apps, schema_editor):
    try:
        from apps.calendar_engine.services.projection import (
            backfill_missing_projections,
        )
        counts = backfill_missing_projections()
        logger.info("Calendar backfill migration complete: %s", counts)
    except Exception:  # noqa: BLE001 - never let a backfill fail the deploy
        logger.warning(
            "Calendar backfill migration skipped (non-fatal)", exc_info=True,
        )


def backwards(apps, schema_editor):
    # Projections are a derived, non-authoritative cache — nothing to reverse.
    # (Source objects are untouched; re-running forwards re-derives them.)
    pass


class Migration(migrations.Migration):

    # Non-atomic: the backfill queries other apps' tables (health/faith/life). On a
    # brand-new database those tables may not exist yet when this runs — the query
    # is caught and skipped (a fresh DB has nothing to backfill anyway), but under a
    # single enclosing transaction that caught error would still poison the migration.
    # Autocommit avoids that. Idempotent, so a partial run is safe to re-apply.
    atomic = False

    dependencies = [
        ('calendar_engine', '0012_availabilityblock_exceptions_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
