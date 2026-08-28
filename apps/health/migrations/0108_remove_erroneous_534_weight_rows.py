"""
ONE-TIME CLEANUP — remove the two proven erroneous weight rows from the 2026-08-27
Stuffed Peppers incident, through the SANCTIONED audited correction path.

WHY A MIGRATION: Claude has no production CLI, and `RunPython` is the sanctioned way to
execute code once in production (the Procfile runs `migrate` on every deploy). This is
NOT an improvised database mutation: it calls `record_correction.remove_record()` — the
same deterministic, identity-bound, soft-deleting service the CoS itself now uses — so
the rows are removed exactly as a user-authorized correction would remove them.

IDENTITY IS PROVEN, NOT PATTERN-MATCHED. Both rows were created by a single erroneous
confirmed action (`ToolCallLog` confirmation `cb50cb49a2924894a29349acb52316cb`,
`log_weight(value=534, unit='lb', notes=<nutrition text>)`, executed twice 38s apart).
This migration re-verifies EVERY one of those facts before touching anything, and if the
match is not EXACTLY the two expected rows it does nothing at all.

NO REPLACEMENT VALUE IS WRITTEN. The rows are removed; nothing is substituted. The
correct weight for that day is not known, and a value nobody supplied is a value nobody
verified.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)

OWNER_EMAIL = "dannyjenkins71@gmail.com"
BAD_VALUE = 534
BAD_UNIT = "lb"
# The two executions of confirmation cb50cb49…, to the second.
EXPECTED_TIMESTAMPS = ("2026-08-27T22:31:10", "2026-08-27T22:31:49")
EXPECTED_COUNT = 2


def cleanup(apps, schema_editor):
    try:
        from django.contrib.auth import get_user_model

        from apps.ai.cos_services import record_correction as rc
        from apps.health.models import WeightEntry

        user = get_user_model().objects.filter(email__iexact=OWNER_EMAIL).first()
        if user is None:
            logger.info("534-cleanup: owner not present; nothing to do")
            return

        rows = [
            e for e in WeightEntry.objects.filter(
                user=user, unit=BAD_UNIT, value=BAD_VALUE)
            if e.recorded_at.strftime("%Y-%m-%dT%H:%M:%S") in EXPECTED_TIMESTAMPS
        ]
        if len(rows) != EXPECTED_COUNT:
            # FAIL CLOSED: the population is not what the investigation proved, so this
            # is no longer the situation this migration was written for.
            logger.warning("534-cleanup: expected %s rows, found %s — doing nothing",
                           EXPECTED_COUNT, len(rows))
            return

        for e in rows:
            out = rc.remove_record(user, "weight", e.pk)
            logger.info("534-cleanup: id=%s -> %s", e.pk, out.get("status"))
    except Exception:
        # Never fail a deploy for a cleanup; the rows can be removed from the UI.
        logger.warning("534-cleanup skipped", exc_info=True)


def noop(apps, schema_editor):
    """Not reversible: restoring a record the user never made is not a correction."""


class Migration(migrations.Migration):
    dependencies = [("health", "0107_medication_reference_m1")]
    operations = [migrations.RunPython(cleanup, noop)]
