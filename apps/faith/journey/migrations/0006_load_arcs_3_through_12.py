"""
Data migration: Load Arcs 3-12 (Covenant & Wilderness through End & New Beginning).

This migration completes "Walking With God Through Scripture" in production —
loading the final 10 arcs that cover Exodus 21 through Revelation, bringing
the journey to its full canonical sweep (12 arcs total).

Uses the proven defensive pattern from 0004 and 0005:
  - Call load_journey_path to upsert all arcs from disk
  - Force is_active=True on every expected arc via direct ORM as a safety net
  - print() statements throughout so Railway deploy logs show what happened
  - Idempotent — safe to re-run

Required because Railway has no CLI access; data migrations are the only
path to populate production. Procfile's `migrate --noinput` triggers this
on every deploy.
"""

import sys

from django.core.management import call_command
from django.db import migrations


def _log(msg):
    print(f"[journey.0006] {msg}", file=sys.stdout, flush=True)


# The 10 arcs this migration is responsible for activating.
# Slugs must match exactly the slug field in each arc's JSON content pack.
EXPECTED_ARC_SLUGS = [
    "covenant_and_wilderness",
    "into_the_promised_land",
    "kings_and_kingdom",
    "prophets_and_exile",
    "return_and_waiting",
    "the_coming_of_jesus",
    "cross_and_empty_tomb",
    "the_church_begins",
    "letters_to_the_churches",
    "end_and_new_beginning",
]


def load_arcs_3_to_12(apps, schema_editor):
    # Use migration-frozen models — schema-safe across future model edits.
    JourneyPath = apps.get_model("journey", "JourneyPath")
    JourneyArc = apps.get_model("journey", "JourneyArc")
    JourneyDay = apps.get_model("journey", "JourneyDay")

    _log("=== START: Arcs 3-12 load ===")

    # State BEFORE
    arcs_before = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_before = JourneyDay.objects.count()
    _log(f"BEFORE: arcs={len(arcs_before)}, total days={days_before}")

    # Belt-and-suspenders: run the loader ONCE PER expected arc using
    # --arc-slug. Determinism: each call is isolated to its named file, so
    # future arc files added to disk cannot retroactively mutate this
    # migration. Per-arc try/except preserves the historical tolerance for
    # missing content packs (arcs 10 and 11 were not yet authored when this
    # migration shipped — they log a warning and are skipped).
    loader_ok = True
    loaded_arcs = []
    skipped_arcs = []
    for arc_slug in EXPECTED_ARC_SLUGS:
        try:
            call_command(
                "load_journey_path",
                "walking_with_god",
                arc_slug=arc_slug,
                verbosity=0,
            )
            loaded_arcs.append(arc_slug)
        except Exception as exc:
            loader_ok = False
            skipped_arcs.append((arc_slug, repr(exc)))
            _log(f"LOADER: arc '{arc_slug}' SKIPPED ({exc!r})")
    _log(f"LOADER: arcs loaded={loaded_arcs}")
    if skipped_arcs:
        _log(f"LOADER: arcs skipped={skipped_arcs}")

    # Force-correct visibility on every expected arc.
    activated = []
    missing = []
    for slug in EXPECTED_ARC_SLUGS:
        arc = JourneyArc.objects.filter(slug=slug).first()
        if arc is None:
            missing.append(slug)
            continue
        if not arc.is_active:
            arc.is_active = True
            arc.save(update_fields=["is_active", "updated_at"])
            activated.append(f"{slug} (force-activated)")
        else:
            activated.append(f"{slug} (already active, days={arc.days.count()})")
    _log(f"ACTIVATED: {activated}")
    if missing:
        _log(f"WARNING: missing arcs not found in DB: {missing}")
        _log("This means their content packs were not on disk during migration.")

    # Re-confirm path & Arc 1/2 stay active (no regression).
    path = JourneyPath.objects.filter(slug="walking_with_god").first()
    if path and (not path.is_active or not path.is_featured):
        path.is_active = True
        path.is_featured = True
        path.save(update_fields=["is_active", "is_featured", "updated_at"])
        _log(f"PATH re-activated: pk={path.pk}")

    for prior_slug in ("creation_to_egypt", "slavery_to_deliverance"):
        arc = JourneyArc.objects.filter(slug=prior_slug).first()
        if arc and not arc.is_active:
            arc.is_active = True
            arc.save(update_fields=["is_active", "updated_at"])
            _log(f"PRIOR arc {prior_slug} re-activated")

    # State AFTER
    arcs_after = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_after = JourneyDay.objects.count()
    _log(f"AFTER: arcs={len(arcs_after)}, total days={days_after}")

    visible_count = JourneyArc.objects.filter(
        is_active=True,
        journey_path__slug="walking_with_god",
    ).count()
    _log(
        f"FINAL: visible_arcs={visible_count}/{len(EXPECTED_ARC_SLUGS) + 2}, "
        f"total_days={days_after}, loader_ok={loader_ok}"
    )
    _log("=== END: Arcs 3-12 load ===")


def reverse(apps, schema_editor):
    """No-op — corrective forward-only data migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journey", "0005_load_arc_2_slavery_to_deliverance"),
    ]

    operations = [
        migrations.RunPython(load_arcs_3_to_12, reverse),
    ]
