"""Bring already-imported genealogy up to the evidence-based relationship standard.

For every user who imported a GEDCOM: backfill Person.sex from the stored import
chunks, upgrade generic 'parent of' bonds to biological father/mother by that sex,
and infer step-parents from marriages — so existing users get correct Canonical
Truth WITHOUT re-importing their file. Idempotent and safe to re-run.
"""

from django.db import migrations


def _log(msg):
    print("[0027] %s" % msg, flush=True)


def _refine(apps, schema_editor):
    from django.contrib.auth import get_user_model
    from apps.legacy.models import ImportChunk
    from apps.legacy.services.import_engine import refine_existing_family_types

    User = get_user_model()
    # `.order_by()` CLEARS ImportChunk.Meta.ordering (= ['index']) before DISTINCT.
    # Without it, Django injects the ORDER BY column into the SELECT, so the query
    # becomes `SELECT DISTINCT (user_id, index)` — distinct on (user, chunk-index)
    # PAIRS, i.e. ~one row per GEDCOM individual (1834 for a 1800-person tree), not
    # distinct users. That turned this into ~1800 redundant refine passes (15–20 min).
    # Clearing the ordering makes DISTINCT mean distinct USERS (~10). The set() is a
    # belt-and-suspenders guard so Meta.ordering can never silently break this again.
    user_ids = set(ImportChunk.objects.filter(chunk_kind="gedcom_person")
                   .order_by()
                   .values_list("batch__user_id", flat=True)
                   .distinct())
    _log("refining %d user(s) with imported genealogy" % len(user_ids))
    for uid in user_ids:
        if uid is None:
            continue
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        try:
            sex_set, upgraded = refine_existing_family_types(user)
            _log("user %s: sex+%d parents+%d" % (uid, sex_set, upgraded))
        except Exception as exc:   # never let one user's data block the deploy
            _log("user %s: SKIPPED (%s)" % (uid, exc))


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("legacy", "0026_person_sex"),
    ]

    operations = [
        migrations.RunPython(_refine, _noop),
    ]
