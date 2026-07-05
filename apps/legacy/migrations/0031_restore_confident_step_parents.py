"""Restore step-parents supported by OVERWHELMING evidence, for already-imported users.

Migration 0030 removed the promiscuous inferred step-parents (marriage → step for every
spouse). This adds back only the ones the evidence clearly supports: a single spouse who
married the child's parent while the child was still a minor. Ambiguous cases are left
for the Clarification Engine — they are not created here.
"""

from django.db import migrations


def _log(msg):
    print("[0031] %s" % msg, flush=True)


def _restore(apps, schema_editor):
    from django.contrib.auth import get_user_model
    from apps.legacy.models import ImportChunk, Relationship
    from apps.legacy.services.import_engine import analyze_step_candidates

    User = get_user_model()
    user_ids = set(ImportChunk.objects.filter(chunk_kind="gedcom_person")
                   .order_by().values_list("batch__user_id", flat=True))
    _log("restoring confident step-parents for %d user(s)" % len([u for u in user_ids if u]))
    for uid in user_ids:
        if uid is None:
            continue
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        try:
            infer, _clarify = analyze_step_candidates(user)
            created = 0
            for spouse_id, child_id, rtype in infer:
                if Relationship.objects.filter(
                        user=user, from_person_id=spouse_id, to_person_id=child_id).exists():
                    continue
                Relationship.objects.create(user=user, from_person_id=spouse_id,
                                            to_person_id=child_id, relationship_type=rtype)
                created += 1
            _log("user %s: +%d confident step-parent(s)" % (uid, created))
        except Exception as exc:   # never let one user's data block the deploy
            _log("user %s: SKIPPED (%s)" % (uid, exc))


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("legacy", "0030_remove_inferred_step_parents"),
    ]

    operations = [
        migrations.RunPython(_restore, _noop),
    ]
