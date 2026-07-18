"""Phase 0c-A — populate canonical people.Person from the LIVING identity stores
(relationships.Person + ai_relationships.Person). Genealogy (legacy.Person) is a
separate identity domain migrated in 0c-B.

Forward-only + idempotent: keyed on PersonSourceLink(source_domain, source_pk), so a
re-run relinks nothing. Non-atomic so each canonical write commits independently (the
seam is per-call atomic) — safe on large data and safe to resume. Correction is a NEW
forward migration, never an un-migration of production identity (reverse is a no-op).

Reads the legacy tables via historical models; drives the canonical seam
(reconciliation.ingest_source_person). Adds rows to people_* ONLY — never mutates or
deletes a legacy row, never redirects a consumer.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    # Historical source models (safe field reads); the canonical side uses the real
    # people services, exactly as the reconciliation seam is designed to be driven.
    PersonA = apps.get_model("relationships", "Person")
    PersonC = apps.get_model("ai_relationships", "Person")
    from apps.people.services.backfill import backfill_living_people

    summary = backfill_living_people(PersonA, PersonC)
    # Surfaced in migrate output for auditability.
    print(f"  [0c-A] living-people backfill: {summary}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("people", "0001_initial"),
        ("relationships", "0005_backfill_relationships_richtext"),
        ("ai_relationships", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
