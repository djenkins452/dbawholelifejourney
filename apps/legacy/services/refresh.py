"""Smart Refresh — synchronize an already-imported source instead of re-importing it.

Import is the initial load; Refresh synchronizes Canonical Truth. A refresh NEVER
duplicates and NEVER erodes user-entered enhancements: existing people are matched by
gedcom xref and only their BLANK facts are filled; user-edited relationships are left
untouched; new people/relationships/facts are added; nothing is deleted. Every refresh
produces a permanent audit summary.
"""

from django.db.models import Q
from django.utils import timezone


def _incoming_signatures(batch):
    xrefs, names = set(), set()
    for ch in batch.chunks.filter(chunk_kind="gedcom_person"):
        d = ch.data or {}
        x = (d.get("xref") or "").strip()
        if x:
            xrefs.add(x)
        nm = (d.get("name") or "").strip().lower()
        if nm:
            names.add((nm, d.get("birth_year")))
    return xrefs, names


def detect_existing_source(user, batch):
    """Has this family already been imported? Compare the upload's individuals (by
    gedcom xref, and name+birth-year as a fallback) against every prior GEDCOM lineage.
    Returns the matching ORIGINAL batch when the overlap is strong, else None."""
    from apps.legacy.models import ImportBatch, Person

    _new_xrefs, new_names = _incoming_signatures(batch)
    if not new_names:
        return None

    # Identity comes from name (+ birth year), NEVER the gedcom xref: xrefs are
    # file-local, so every export reuses @I1@/@I2@ for different people. Two exports of
    # the SAME tree share the same PEOPLE.
    best, best_score = None, 0
    candidates = (ImportBatch.all_objects
                  .filter(user=user, source_type="gedcom", is_refresh=False)
                  .exclude(pk=batch.pk))
    for cand in candidates:
        cnames = {((n or "").strip().lower(), by) for n, by in
                  Person.all_objects.filter(user=user, source_batch=cand)
                  .values_list("display_name", "birth_year")}
        score = len(new_names & cnames)
        if score > best_score:
            best, best_score = cand, score

    if best is None:
        return None
    floor = max(2, int(0.3 * len(new_names)))
    return best if best_score >= floor else None


def _existing_lineage_people(original):
    from apps.legacy.models import Person
    return {p.gedcom_xref: p for p in
            Person.all_objects.filter(user=original.user, source_batch=original)
            .exclude(gedcom_xref="")}


def diff_refresh(original, incoming):
    """A preview of what a refresh WOULD change — computed against the current tree,
    committing nothing. People counts are exact; relationships/facts are an estimate
    (the exact deltas appear in the post-refresh audit)."""
    from apps.legacy.models import Relationship

    user = original.user
    existing = _existing_lineage_people(original)

    people_new = people_updated = people_unchanged = 0
    incoming_xrefs = set()
    xref_to_pk = {x: p.pk for x, p in existing.items()}
    for ch in incoming.chunks.filter(chunk_kind="gedcom_person"):
        d = ch.data or {}
        x = (d.get("xref") or "").strip()
        incoming_xrefs.add(x)
        p = existing.get(x)
        if not p:
            people_new += 1
        elif ((p.birth_date is None and d.get("birth_date"))
                or (p.death_date is None and d.get("death_date"))
                or (not p.birth_year and d.get("birth_year"))
                or (not p.death_year and d.get("death_year"))
                or (not p.sex and d.get("sex"))):
            people_updated += 1
        else:
            people_unchanged += 1

    no_longer = [x for x in existing if x not in incoming_xrefs]

    # Estimate NEW relationships: incoming parent/couple pairs not already present.
    existing_pairs = set()
    for a, b in Relationship.objects.filter(user=user).values_list(
            "from_person_id", "to_person_id"):
        existing_pairs.add((a, b))
        existing_pairs.add((b, a))
    rel_new = 0
    for ch in incoming.chunks.filter(chunk_kind="gedcom_family"):
        d = ch.data or {}
        husb, wife = xref_to_pk.get(d.get("husb")), xref_to_pk.get(d.get("wife"))
        pairs = []
        if husb and wife:
            pairs.append((husb, wife))
        for cx in (d.get("children") or []):
            child = xref_to_pk.get(cx)
            for par in (husb, wife):
                if par and child:
                    pairs.append((par, child))
                elif par or child:
                    rel_new += 1        # a link touching a brand-new person
        for pr in pairs:
            if pr not in existing_pairs:
                rel_new += 1

    facts_incoming = sum(
        len((ch.data or {}).get("facts", []))
        for ch in incoming.chunks.filter(chunk_kind__in=["gedcom_person", "gedcom_family"]))

    return {
        "people_new": people_new,
        "people_updated": people_updated,
        "people_unchanged": people_unchanged,
        "matched_people": len(existing.keys() & incoming_xrefs),
        "no_longer_present": no_longer,
        "relationships_new": rel_new,
        "facts_incoming": facts_incoming,
        "unsupported": (incoming.coverage or {}).get("needs_support", []),
        "unknown": (incoming.coverage or {}).get("unknown", []),
    }


def apply_refresh(original, incoming):
    """Synchronize `original`'s lineage from the newer `incoming` upload, then record a
    permanent audit. Delegates the actual write to the idempotent, conflict-safe
    genealogy commit (people matched by xref; blanks filled; user edits protected)."""
    from apps.legacy.models import PreservedFact, Relationship, Person
    from apps.legacy.services.import_engine import commit_genealogy

    user = original.user
    pre = diff_refresh(original, incoming)
    before_people = Person.all_objects.filter(user=user, source_batch=original).count()
    before_rels = Relationship.objects.filter(user=user).count()
    before_facts = PreservedFact.objects.filter(user=user).count()

    commit_genealogy(original, chunks_from=incoming)

    after_people = Person.all_objects.filter(user=user, source_batch=original).count()
    after_rels = Relationship.objects.filter(user=user).count()
    after_facts = PreservedFact.objects.filter(user=user).count()

    audit = {
        "when": timezone.now().isoformat(),
        "source_name": incoming.source_name,
        "people_added": after_people - before_people,
        "people_updated": pre["people_updated"],
        "relationships_added": after_rels - before_rels,
        "facts_preserved": after_facts - before_facts,
        "unchanged": pre["people_unchanged"],
        "no_longer_in_source": len(pre["no_longer_present"]),
        # Everything that already existed and was matched/kept rather than duplicated.
        "duplicates_prevented": pre["matched_people"] + before_rels + before_facts,
        "unsupported": pre["unsupported"],
        "unknown": pre["unknown"],
    }

    incoming.is_refresh = True
    incoming.refresh_of = original
    incoming.refresh_summary = audit
    incoming.import_status = "complete"
    incoming.save(update_fields=["is_refresh", "refresh_of", "refresh_summary",
                                 "import_status", "updated_at"])
    original.refresh_summary = audit
    original.save(update_fields=["refresh_summary", "updated_at"])
    return audit
