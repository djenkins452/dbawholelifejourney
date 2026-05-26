"""
Data migration: Load Arc 2 — Slavery to Deliverance (Exodus 1-20).

Uses the same defensive pattern proven in 0004:
  - Direct ORM upserts where possible (for critical visibility flags)
  - load_journey_path call as belt-and-suspenders to load day-level content
  - print() statements throughout so Railway deploy logs show exactly what
    happened in production
  - Idempotent — safe to re-run

Required because Railway has no CLI access; data migrations are the only
path to populate production. Procfile's `migrate --noinput` triggers this
on every deploy.
"""

import sys

from django.core.management import call_command
from django.db import migrations


def _log(msg):
    print(f"[journey.0005] {msg}", file=sys.stdout, flush=True)


def load_arc_2(apps, schema_editor):
    # Use migration-frozen models — schema-safe across future model edits.
    JourneyPath = apps.get_model("journey", "JourneyPath")
    JourneyArc = apps.get_model("journey", "JourneyArc")
    JourneyDay = apps.get_model("journey", "JourneyDay")

    _log("=== START: Arc 2 (Slavery to Deliverance) load ===")

    # State BEFORE
    arcs_before = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_before = JourneyDay.objects.count()
    _log(f"BEFORE: arcs={arcs_before}, total days={days_before}")

    # Belt-and-suspenders: run the loader for ONLY this arc. Determinism:
    # --arc-slug isolates the migration from future content added on disk.
    loader_ok = False
    try:
        call_command(
            "load_journey_path",
            "walking_with_god",
            arc_slug="slavery_to_deliverance",
            verbosity=0,
        )
        loader_ok = True
        _log("LOADER: load_journey_path arc='slavery_to_deliverance' succeeded")
    except Exception as exc:
        _log(f"LOADER FAILED (will continue with manual enforcement): {exc!r}")

    # Force-correct visibility for Arc 2 if the loader didn't set it.
    arc2 = JourneyArc.objects.filter(slug="slavery_to_deliverance").first()
    if arc2 is None:
        _log(
            "WARNING: slavery_to_deliverance arc NOT FOUND after loader. "
            "Content pack may be missing from container. Arc 2 not live."
        )
    else:
        if not arc2.is_active:
            arc2.is_active = True
            arc2.save(update_fields=["is_active", "updated_at"])
            _log(f"ARC 2 force-activated: pk={arc2.pk}")
        else:
            _log(f"ARC 2 already active: pk={arc2.pk}, days={arc2.days.count()}")

    # Also re-confirm path & Arc 1 stay active (no regression of Arc 1)
    path = JourneyPath.objects.filter(slug="walking_with_god").first()
    if path and not path.is_active:
        path.is_active = True
        path.is_featured = True
        path.save(update_fields=["is_active", "is_featured", "updated_at"])
        _log(f"PATH re-activated (had become inactive somehow): pk={path.pk}")

    arc1 = JourneyArc.objects.filter(slug="creation_to_egypt").first()
    if arc1 and not arc1.is_active:
        arc1.is_active = True
        arc1.save(update_fields=["is_active", "updated_at"])
        _log(f"ARC 1 re-activated (had become inactive somehow): pk={arc1.pk}")

    # State AFTER
    arcs_after = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_after = JourneyDay.objects.count()
    _log(f"AFTER: arcs={arcs_after}, total days={days_after}")

    arc1_visible = JourneyArc.objects.filter(
        journey_path=path, slug="creation_to_egypt", is_active=True
    ).exists() if path else False
    arc2_visible = JourneyArc.objects.filter(
        journey_path=path, slug="slavery_to_deliverance", is_active=True
    ).exists() if path else False
    _log(
        f"FINAL: arc_1 visible? {'YES' if arc1_visible else 'NO'} | "
        f"arc_2 visible? {'YES' if arc2_visible else 'NO'} | "
        f"loader_ok={loader_ok}"
    )
    _log("=== END: Arc 2 load ===")


def reverse(apps, schema_editor):
    """No-op on reverse — corrective forward-only data migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journey", "0004_force_arc_1_active_state"),
    ]

    operations = [
        migrations.RunPython(load_arc_2, reverse),
    ]
