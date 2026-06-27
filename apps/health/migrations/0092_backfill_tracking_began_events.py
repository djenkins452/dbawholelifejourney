"""
Sprint 2A/2E — backfill the MedicationEvent ledger for existing medications.

Forward-only history (Medication Intelligence Canon): WLJ has no record of prior
dose changes, so we DO NOT fabricate any. Each existing ACTIVE intake receives
exactly ONE honest ``tracking_began`` event dated at its ``start_date`` (or
``created_at`` if start_date is null). The timeline can then state truthfully:
"Tracking began on <date>. Earlier history was not recorded."

Idempotent: skips any intake that already has events. Reversible: the reverse
removes only the backfilled ``tracking_began`` events.
"""

from django.db import migrations


def backfill_tracking_began(apps, schema_editor):
    Intake = apps.get_model("health", "Intake")
    MedicationEvent = apps.get_model("health", "MedicationEvent")

    # Active intakes only (status=active record existence + clinical active).
    active = Intake.objects.filter(status="active", intake_status="active")
    to_create = []
    for intake in active.iterator():
        if MedicationEvent.objects.filter(intake=intake).exists():
            continue  # idempotent — never double-backfill
        effective = intake.start_date or (
            intake.created_at.date() if intake.created_at else None
        )
        if effective is None:
            continue
        to_create.append(
            MedicationEvent(
                user_id=intake.user_id,
                intake=intake,
                event_type="tracking_began",
                effective_date=effective,
                previous_value=None,
                new_value={"name": intake.name, "dose": intake.dose},
                reason="backfill",
                reason_detail="Tracking began. Earlier history was not recorded.",
                source="backfill",
                # status/created_at handled by model defaults on the historical model
            )
        )
    if to_create:
        MedicationEvent.objects.bulk_create(to_create, batch_size=500)


def remove_tracking_began(apps, schema_editor):
    MedicationEvent = apps.get_model("health", "MedicationEvent")
    MedicationEvent.objects.filter(
        event_type="tracking_began", source="backfill"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("health", "0091_medicationevent"),
    ]

    operations = [
        migrations.RunPython(backfill_tracking_began, remove_tracking_began),
    ]
