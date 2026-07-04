"""Repair Canonical Truth: remove marriages the old importer INFERRED.

The previous GEDCOM importer created a "married to" relationship for every FAM
record that had a husband and a wife — even when the record carried no marriage
evidence. A GEDCOM family is a family UNIT, not proof of marriage. This migration
walks every imported family and, where there was no marriage evidence (no marriage
year / date / place, and no `couple_type`), deletes the spurious spouse
relationship. The couple remain connected through their children.

O(N): one pass over people, family chunks, and married relationships — no per-row
queries. Idempotent (a second run finds nothing to remove).
"""

from django.db import migrations


def repair(apps, schema_editor):
    Person = apps.get_model("legacy", "Person")
    Relationship = apps.get_model("legacy", "Relationship")
    ImportChunk = apps.get_model("legacy", "ImportChunk")

    # (source_batch_id, gedcom_xref) -> person_id
    pmap = {}
    for pid, batch_id, xref in (Person.objects.filter(source_batch__isnull=False)
                                .exclude(gedcom_xref="")
                                .values_list("id", "source_batch_id", "gedcom_xref")):
        pmap[(batch_id, (xref or "").strip())] = pid

    # Person-pairs whose "marriage" was inferred (no evidence on the family record).
    spurious = set()
    for data, batch_id in (ImportChunk.objects.filter(chunk_kind="gedcom_family")
                           .values_list("data", "batch_id")):
        d = data or {}
        # Keep only marriages with KNOWN evidence. A family unit with no marriage
        # event is not evidence — its old inferred marriage is removed here and
        # re-surfaced by the clarification engine for the user to resolve. A marriage
        # the user has already clarified as real is kept.
        if d.get("marriage_clarified") == "married":
            has_marriage = True
        elif "marriage_status" in d:
            has_marriage = d.get("couple_type") is not None and d.get("marriage_status") == "known"
        elif "couple_type" in d:
            has_marriage = d["couple_type"] is not None
        else:
            has_marriage = bool(d.get("marriage_year") or d.get("marriage_date")
                                or d.get("marriage_place"))
        if has_marriage:
            continue
        h = (d.get("husb") or "").strip()
        w = (d.get("wife") or "").strip()
        if not h or not w:
            continue
        hp = pmap.get((batch_id, h))
        wp = pmap.get((batch_id, w))
        if hp and wp:
            spurious.add(frozenset((hp, wp)))

    if not spurious:
        return

    # Delete the inferred "married to" links for those pairs (both directions).
    # Real marriages ("former spouse of", or any with evidence) are never touched.
    doomed = []
    for rid, fp, tp in (Relationship.objects.filter(relationship_type__icontains="married")
                        .values_list("id", "from_person_id", "to_person_id")):
        if frozenset((fp, tp)) in spurious:
            doomed.append(rid)
    if doomed:
        Relationship.objects.filter(id__in=doomed).delete()


def noop(apps, schema_editor):
    # Not reversible — we cannot know which removed marriages to recreate, and we
    # would only be restoring incorrect data.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("legacy", "0024_preservedfact"),
    ]

    operations = [
        migrations.RunPython(repair, noop),
    ]
