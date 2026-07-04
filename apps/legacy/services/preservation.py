"""Legacy's permanent preservation layer.

The promise: Legacy never intentionally discards meaningful information. Every
imported fact that Canonical Truth cannot yet model is written to a durable
``PreservedFact`` row — tied to the Person it describes and grouped by the CONCEPT
it belongs to (Career, Faith Journey, Military, Life Events…). When a canonical
domain is later built, it backfills straight from these rows: no user ever
re-imports a file. The Canonical Truth Roadmap is an aggregation of this layer.
"""

import hashlib

from apps.legacy.services.gedcom_parser import classify_fact, UNKNOWN_CONCEPT


def _dedupe_key(user_id, person_id, subject_label, tag, value, date, place):
    raw = "|".join(str(x) for x in (
        user_id, person_id or "", subject_label or "", tag, value, date, place))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def preserve_facts(user, batch, person, subject_label, facts):
    """Persist every needs_support / unknown fact as a permanent PreservedFact.
    Supported and structural facts are skipped (they already live in Canonical
    Truth). Idempotent — re-committing a batch never duplicates a fact. Returns the
    number of NEW rows created."""
    from apps.legacy.models import PreservedFact

    created = 0
    for f in facts or []:
        tag = (f.get("tag") or "").strip()
        if not tag:
            continue
        status, label, concept = classify_fact(tag)
        if status in ("supported", "structural"):
            continue
        value = (f.get("value") or "")[:2000]
        date = (f.get("date") or "")[:80]
        place = (f.get("place") or "")[:255]
        key = _dedupe_key(user.id, person.id if person else None,
                          subject_label, tag, value, date, place)
        fact_status = (PreservedFact.FactStatus.UNKNOWN if status == "unknown"
                       else PreservedFact.FactStatus.AWAITING)
        _, made = PreservedFact.objects.get_or_create(
            user=user, dedupe_key=key,
            defaults=dict(
                source_batch=batch, person=person,
                subject_label=(subject_label or "")[:200], source_format="gedcom",
                concept=concept, label=label[:80], original_tag=tag[:40],
                value=value, fact_date=date, fact_place=place,
                original_data=f, fact_status=fact_status))
        if made:
            created += 1
    return created


def preservation_roadmap(user):
    """The Canonical Truth Roadmap — the permanent preservation layer aggregated by
    CONCEPT, built entirely from real imported data (never brainstorming). Each row
    carries a count, the granular fact-types seen, representative examples, and a
    status. This is the evidence-driven roadmap for how Canonical Truth should grow."""
    from django.db.models import Count

    from apps.legacy.models import PreservedFact

    qs = PreservedFact.objects.filter(user=user)
    rows = qs.values("concept").annotate(n=Count("id")).order_by("-n")
    out = []
    total = 0
    for r in rows:
        concept, n = r["concept"], r["n"]
        total += n
        cqs = qs.filter(concept=concept)
        labels = sorted(set(cqs.values_list("label", flat=True)))
        examples = [pf.summary for pf in cqs.order_by("-created_at")[:4]]
        statuses = set(cqs.values_list("fact_status", flat=True))
        if statuses == {PreservedFact.FactStatus.MODELED}:
            status = "modeled"
        elif concept == UNKNOWN_CONCEPT:
            status = "unknown"
        else:
            status = "awaiting"
        out.append({"concept": concept, "count": n, "labels": labels,
                    "examples": examples, "status": status})
    return {"concepts": out, "total": total, "people_touched": (
        qs.exclude(person__isnull=True).values("person").distinct().count())}
