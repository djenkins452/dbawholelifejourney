"""
Defensive data migration: force Arc 1 (Creation to Egypt) into is_active=True
state for production.

WHY THIS EXISTS:
    Production validation after commit c48d2d9d showed users still seeing
    "The journey isn't open yet" at /faith/journey/today/. This means
    JourneyPath.objects.filter(slug='walking_with_god', is_active=True)
    returned None in production even though path.json has is_active=true
    and migration 0003_load_arc_1_creation_to_egypt should have set it.

    Rather than continue diagnosing why 0003 didn't take effect (no CLI
    access to production), this migration force-corrects the state via
    direct ORM updates. Bypasses the loader. Idempotent. Prints state
    transitions so Railway deploy logs will show exactly what happened.

WHAT IT DOES:
    1. Logs current state of JourneyPath / JourneyArc / JourneyDay
    2. Upserts JourneyPath(slug='walking_with_god') with is_active=True
       and is_featured=True via direct ORM (no loader)
    3. Re-runs load_journey_path as a belt-and-suspenders measure to
       ensure the 7 days are loaded (idempotent upsert)
    4. Explicitly sets is_active=True on the creation_to_egypt arc
       (in case the loader's value didn't take)
    5. Logs final state

IDEMPOTENT: safe to re-run any number of times.
"""

import sys

from django.core.management import call_command
from django.db import migrations


def _log(msg):
    """Print to deploy logs — Railway captures stdout from migrations."""
    print(f"[journey.0004] {msg}", file=sys.stdout, flush=True)


def force_arc_1_active(apps, schema_editor):
    # Use the LIVE models — this migration runs after all schema migrations,
    # so the current ORM is safe.
    from apps.faith.journey.models import JourneyArc, JourneyDay, JourneyPath

    _log("=== START: Defensive Arc 1 activation ===")

    # 1) State BEFORE any action.
    paths_before = list(JourneyPath.objects.values("slug", "name", "is_active", "is_featured"))
    arcs_before = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_count_before = JourneyDay.objects.count()
    _log(f"BEFORE: paths={paths_before}")
    _log(f"BEFORE: arcs={arcs_before}")
    _log(f"BEFORE: total JourneyDay rows = {days_count_before}")

    # 2) Force-upsert the JourneyPath via direct ORM. No loader dependency.
    path, created = JourneyPath.objects.update_or_create(
        slug="walking_with_god",
        defaults={
            "name": "Walking With God Through Scripture",
            "narrative_overview": (
                "A guided walk through the story of God — slow, contextual, "
                "plain-English. Built for people who want to finally understand "
                "Scripture rather than rush through it. Each day teaches the "
                "setting before the reading, explains in plain English after, "
                "and offers one small step to live what was learned."
            ),
            "cover_image_url": "",
            "estimated_weeks": 52,
            "difficulty_default": "standard",
            "is_active": True,
            "is_featured": True,
        },
    )
    _log(f"PATH upsert: created={created}, pk={path.pk}, is_active={path.is_active}")

    # 3) Drop any legacy arc that shouldn't be there. Safe — never user-facing.
    legacy_deleted, _ = JourneyArc.objects.filter(slug="egypt_to_tabernacle").delete()
    _log(f"LEGACY arc deletion: rows removed = {legacy_deleted}")

    # 4) Belt-and-suspenders: run the loader to upsert days from disk.
    #    If the content pack is in the container, this loads all 7 days.
    #    If for some reason the pack is missing, we catch and log, then
    #    proceed to manual arc enforcement below.
    loader_ok = False
    try:
        call_command("load_journey_path", "walking_with_god", verbosity=0)
        loader_ok = True
        _log("LOADER: load_journey_path('walking_with_god') succeeded")
    except Exception as exc:
        _log(f"LOADER FAILED (continuing with manual enforcement): {exc!r}")

    # 5) Force is_active on the arc — in case the loader's value didn't stick.
    arc = JourneyArc.objects.filter(journey_path=path, slug="creation_to_egypt").first()
    if arc is not None:
        if not arc.is_active:
            arc.is_active = True
            arc.save(update_fields=["is_active", "updated_at"])
            _log(f"ARC force-activated: slug={arc.slug}, pk={arc.pk}")
        else:
            _log(f"ARC already active: slug={arc.slug}, pk={arc.pk}")
    else:
        _log(
            "WARNING: creation_to_egypt arc NOT FOUND after loader run. "
            "Content pack may be missing from the deployed container. "
            "The arc must be created via load_journey_path or admin."
        )

    # 6) State AFTER.
    paths_after = list(JourneyPath.objects.values("slug", "name", "is_active", "is_featured"))
    arcs_after = list(JourneyArc.objects.values("slug", "is_active", "order"))
    days_count_after = JourneyDay.objects.count()
    _log(f"AFTER: paths={paths_after}")
    _log(f"AFTER: arcs={arcs_after}")
    _log(f"AFTER: total JourneyDay rows = {days_count_after}")

    # 7) Final assertion-as-log: did we hit the user-visible target?
    visible_path = JourneyPath.objects.filter(
        slug="walking_with_god", is_active=True
    ).first()
    _log(
        f"FINAL: walking_with_god visible to users? "
        f"{'YES' if visible_path else 'NO'} (loader_ok={loader_ok})"
    )
    _log("=== END: Defensive Arc 1 activation ===")


def reverse(apps, schema_editor):
    """No-op on reverse — this is a corrective forward-only migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("journey", "0003_load_arc_1_creation_to_egypt"),
    ]

    operations = [
        migrations.RunPython(force_arc_1_active, reverse),
    ]
