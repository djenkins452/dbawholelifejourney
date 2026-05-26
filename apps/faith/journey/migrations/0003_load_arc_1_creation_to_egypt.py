"""
Data migration: Load Arc 1 — Creation to Egypt.

Required for production deployment because Railway has no CLI access to
run management commands manually (see CLAUDE.md). Data migrations run
automatically via Procfile `python manage.py migrate --noinput`, so this
migration is how the Arc 1 content reaches the production database.

Operations:
    1. Delete the legacy egypt_to_tabernacle arc + its day (was a reality-
       check only; never user-facing, never activated).
    2. Invoke the load_journey_path command to upsert the Arc 1 content
       pack from disk.
"""

from django.core.management import call_command
from django.db import migrations


def load_arc_1(apps, schema_editor):
    """Load Arc 1 — Creation to Egypt from the JSON content pack.

    Determinism contract: this migration explicitly loads ONLY the
    ``creation_to_egypt`` arc via ``--arc-slug``. Future arc files added to
    ``apps/faith/journey/content/walking_with_god/arcs/`` do not affect this
    migration. A fresh DB in 2028 will replay exactly what was authored in 2026.
    """
    # Remove the legacy reality-check arc if it's present.
    # We use the historical model so the migration is faithful to its schema epoch.
    JourneyArc = apps.get_model("journey", "JourneyArc")
    JourneyArc.objects.filter(slug="egypt_to_tabernacle").delete()

    # Single-arc load. The loader uses update_or_create and runs inside its own
    # transaction. Arc-slug filtering is strictly filename-based, so no other
    # JSON file on disk will be read or validated.
    call_command("load_journey_path", "walking_with_god", arc_slug="creation_to_egypt")


def reverse(apps, schema_editor):
    """No-op on reverse.

    The data state created by this migration is not meaningfully
    reversible (it's idempotent content load). Rolling back the migration
    leaves the loaded rows in place; subsequent re-application is safe.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journey", "0002_userjourney_last_visited_at"),
    ]

    operations = [
        migrations.RunPython(load_arc_1, reverse),
    ]
