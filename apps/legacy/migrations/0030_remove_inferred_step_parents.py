"""Remove the step-parents the old marriage-based inference invented.

The retired algorithm made every spouse of a parent a step-parent of that parent's
children — so someone could end up with many "parents" (Danny had seven). Step-parents
are EVIDENCE-BASED only: a step bond is legitimate when the child is actually recorded
as a child in that step-parent's family (an explicit step pedigree, _FREL/_MREL/PEDI).

This deletes step relationships that are NOT backed by that evidence and were NOT edited
by the user. User-corrected relationships are always kept. Anything genuinely ambiguous
is left for the Clarification Engine to ask about — never re-invented.
"""

from django.db import migrations


def _log(msg):
    print("[0030] %s" % msg, flush=True)


def _cleanup(apps, schema_editor):
    from apps.legacy.models import ImportChunk, Person, Relationship

    # distinct USERS with imported genealogy — .order_by() clears ImportChunk.Meta
    # ordering so DISTINCT means users, not (user, index) pairs (see 0027).
    user_ids = set(ImportChunk.objects.filter(chunk_kind="gedcom_person")
                   .order_by().values_list("batch__user_id", flat=True))
    _log("cleaning step-parents for %d user(s)" % len([u for u in user_ids if u]))

    for uid in user_ids:
        if uid is None:
            continue
        try:
            # Map (lineage batch, gedcom xref) -> person pk.
            by_key = {}
            for sb, xref, pk in (Person.all_objects
                                 .filter(user_id=uid, source_batch__isnull=False)
                                 .exclude(gedcom_xref="")
                                 .values_list("source_batch_id", "gedcom_xref", "pk")):
                by_key[(sb, xref)] = pk

            # (parent_pk, child_pk) pairs that ACTUALLY appear as family membership in
            # the source — the only place a legitimate step bond can come from.
            membership = set()
            for ch in (ImportChunk.objects.filter(batch__user_id=uid,
                                                  chunk_kind="gedcom_family")
                       .select_related("batch")):
                d = ch.data or {}
                lineage = ch.batch.refresh_of_id or ch.batch_id
                parents = [by_key.get((lineage, (d.get("husb") or "").strip())),
                           by_key.get((lineage, (d.get("wife") or "").strip()))]
                for cx in (d.get("children") or []):
                    cpk = by_key.get((lineage, (cx or "").strip()))
                    for ppk in parents:
                        if ppk and cpk:
                            membership.add((ppk, cpk))

            removed = 0
            for r in Relationship.objects.filter(user_id=uid, user_edited=False):
                t = (r.relationship_type or "").lower()
                if "step" in t and (r.from_person_id, r.to_person_id) not in membership:
                    r.delete()
                    removed += 1
            _log("user %s: removed %d invented step-parent(s)" % (uid, removed))
        except Exception as exc:   # never let one user's data block the deploy
            _log("user %s: SKIPPED (%s)" % (uid, exc))


def _noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("legacy", "0029_clarificationdecision"),
    ]

    operations = [
        migrations.RunPython(_cleanup, _noop),
    ]
