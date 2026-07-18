"""Phase 0c-B — populate canonical people.Person from the LEGACY genealogy store
(legacy.Person), a deliberately separate identity domain from living contacts.

CREATE-DISTINCT: never match by name (same-name individuals are normal in a family
tree; GEDCOM identity = source_batch + xref, never name). No People membership
(genealogy stays in the Legacy view). Custom aliases migrate to RecognitionPhrase.

Forward-only + idempotent (PersonSourceLink-keyed) + non-atomic (resumable). Adds rows
to people_* ONLY — never mutates or deletes a legacy row, never redirects a consumer.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    PersonB = apps.get_model("legacy", "Person")
    RelationshipAliasB = apps.get_model("legacy", "RelationshipAlias")
    from apps.people.services.backfill import backfill_legacy_genealogy

    summary = backfill_legacy_genealogy(PersonB, RelationshipAliasB)
    print(f"  [0c-B] legacy-genealogy backfill: {summary}")


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("people", "0002_backfill_living_people"),
        ("legacy", "0037_backfill_legacy_richtext"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
