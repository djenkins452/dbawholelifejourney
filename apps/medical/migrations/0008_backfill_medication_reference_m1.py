"""
ONE-TIME BACKFILL — resolve authoritative labels for medications already on file.

WHY A MIGRATION: Claude has no production CLI or shell; a `RunPython` migration is
the sanctioned way to execute code once in production (the Procfile runs `migrate`
on every deploy). The recurring path is the crontab task
`medical.refresh_medication_reference_labels` — this only stops the first users
from waiting until 05:00 UTC for truth that already exists.

SAFETY: strictly bounded, fully guarded, and idempotent. It performs outbound HTTP
on the RELEASE container (never a request path), caps the work, and can never fail a
deploy — any exception is swallowed, because the crontab will do the same work later.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

BACKFILL_LIMIT = 25


def backfill(apps, schema_editor):
    try:
        from apps.medical.tasks import refresh_medication_reference_labels
        counts = refresh_medication_reference_labels(limit=BACKFILL_LIMIT)
        logger.info("medication_reference backfill: %s", counts)
    except Exception:
        # Never fail a deploy for a cache warm — the crontab retries at 05:00 UTC.
        logger.warning("medication_reference backfill skipped", exc_info=True)


def noop(apps, schema_editor):
    """Reverse is a no-op: the resolved labels are valid truth, not migration state."""


class Migration(migrations.Migration):
    dependencies = [
        ("medical", "0007_medication_reference_m1"),
        ("health", "0107_medication_reference_m1"),
    ]
    operations = [migrations.RunPython(backfill, noop)]
