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
    user_ids = list(ImportChunk.objects.filter(chunk_kind="gedcom_person")
                    .values_list("batch__user_id", flat=True).distinct())
    _log("refining %d user(s) with imported genealogy" % len(user_ids))
    for uid in user_ids:
        if uid is None:
            continue
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        try:
            sex_set, upgraded, steps = refine_existing_family_types(user)
            _log("user %s: sex+%d parents+%d steps+%d" % (uid, sex_set, upgraded, steps))
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
