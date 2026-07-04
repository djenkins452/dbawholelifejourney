"""
One-time repair for genealogy imported before full-date capture and the user
binding existed:
  • bind each user to their canonical Person (fuzzy name match), so Family/People
    open on them without any manual step;
  • backfill exact birth/death dates onto already-committed people from their
    import chunks (structured data or body text).

Non-destructive. Runs on deploy (Procfile migrate). Safe to no-op for users with
no genealogy.
"""

from django.db import migrations


def _log(msg):
    # Printed to stdout so it shows in the Railway deploy log immediately. Lets us
    # tell "running slowly" from "not running / blocked on a lock".
    print("[migration 0020] %s" % msg, flush=True)


def _repair(apps, schema_editor):
    # Use the real services (they lazily import the current models). Guarded so a
    # single bad user can never fail the deploy migration.
    try:
        from apps.legacy.models import Person
        from apps.legacy.services.import_engine import backfill_gedcom_dates
        from apps.legacy.services.self_binding import get_self_person
        from django.contrib.auth import get_user_model
    except Exception as exc:
        _log("imports failed (%r) — skipping repair" % exc)
        return
    User = get_user_model()
    user_ids = list(Person.objects.values_list("user_id", flat=True).distinct())
    _log("START — %d user(s) with people to repair" % len(user_ids))
    for i, uid in enumerate(user_ids, 1):
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        _log("user %d/%d (id=%s): binding keeper…" % (i, len(user_ids), uid))
        try:
            get_self_person(user)     # binds the keeper if resolvable
        except Exception as exc:
            _log("  bind skipped: %r" % exc)
        _log("user %d/%d (id=%s): backfilling dates…" % (i, len(user_ids), uid))
        try:
            n = backfill_gedcom_dates(
                user, progress=lambda seen: _log("  …%d chunks scanned" % seen))
            _log("  backfilled %d people" % n)
        except Exception as exc:
            _log("  backfill skipped: %r" % exc)
    _log("DONE")


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    # Not one giant transaction — each user's O(N) repair commits independently,
    # so this can never hold a long-running lock or stall the whole deploy.
    atomic = False

    dependencies = [
        ("legacy", "0019_person_gedcom_xref_person_source_batch_legacyprofile"),
    ]
    operations = [migrations.RunPython(_repair, _noop)]
