"""
Legacy Import Engine — orchestration.

Document → parse (adapter) → intelligent chunks → (on request) import a chosen
range → each chunk becomes a DRAFT Memory that runs through the SAME Story
Discovery Engine as a hand-written story. Imported memories carry full import
provenance and are reviewed and promoted exactly like manual ones. Nothing
bypasses Canonical Truth, Discovery, or provenance.
"""

import logging

from apps.legacy.services import discovery as discovery_svc
from apps.legacy.services.import_adapters import chunk, get_adapter

logger = logging.getLogger(__name__)


def create_batch(user, source_name, source_type, raw_text, classifier=None):
    """Parse a document into an ImportBatch + pending ImportChunks and CLASSIFY
    what each unit is (story / fact / person / place / milestone / quote / …)
    before anything is imported. Imports nothing. `classifier` is injectable for
    tests (defaults to the OpenAI classification call, which fails safe to story)."""
    from apps.legacy.models import ImportBatch, ImportChunk
    from apps.legacy.services import gedcom_parser, import_classifier

    # ONE importer, auto-routing: a genealogy file is recognized even if the user
    # didn't say so — they just gave Legacy "their life".
    if source_type != "gedcom" and gedcom_parser.looks_like_gedcom(raw_text):
        source_type = "gedcom"

    if source_type == "gedcom":
        # Structured knowledge → parsed straight into pre-classified genealogy
        # chunks. Never flattened into stories, never sent to the AI classifier.
        chunks = gedcom_parser.parse_gedcom(raw_text or "")
    else:
        adapter = get_adapter(source_type)
        segments = adapter(raw_text or "")
        chunks = chunk(segments)

    # Classification precedes extraction. Chunks a structured parser already
    # classified keep their kind; only prose units go to the AI classifier.
    to_classify = [c for c in chunks if not c.get("kind")]
    kinds = import_classifier.classify_chunks(to_classify, classifier=classifier)
    for c in chunks:
        if c.get("kind"):
            kinds[c["index"]] = (c["kind"], c.get("confidence", "high"))

    batch = ImportBatch.objects.create(
        user=user,
        source_name=(source_name or "Untitled document")[:255],
        source_type=source_type,
        total_chunks=len(chunks),
        import_status=ImportBatch.Status.PARSED,
        created_via=ImportBatch.CREATED_VIA_IMPORT,
    )
    rows = []
    for c in chunks:
        kind, conf = kinds.get(c["index"], ("story", ""))
        rows.append(ImportChunk(
            batch=batch, index=c["index"], title=c["title"][:255],
            body=c["body"], source_ref=c["source_ref"][:120],
            chunk_kind=kind, kind_confidence=conf, data=c.get("data") or {}))
    ImportChunk.objects.bulk_create(rows)
    return batch


def import_chunks(batch, indices=None, limit=None, run_discovery=True):
    """
    Import selected pending chunks (by index list and/or a limit). Each becomes a
    DRAFT Memory with import provenance, then goes through Discovery (proposals
    only). Returns the created memories. Never imports everything implicitly.
    """
    from apps.legacy.models import ImportChunk, Memory

    qs = batch.chunks.filter(status=ImportChunk.Status.PENDING).order_by("index")
    if indices:
        # Explicit per-chunk pick — honour the user's choice even if it was
        # classified as something other than a story (a deliberate override).
        qs = qs.filter(index__in=[int(i) for i in indices])
    else:
        # Bulk import ("read the next N / all") only turns NARRATIVE units into
        # story Memories. Facts and entities never silently become stories —
        # they wait in their own review queues.
        qs = qs.filter(chunk_kind__in=list(ImportChunk.NARRATIVE_KINDS))
    pending = list(qs[:limit] if limit else qs)

    memories = []
    for ch in pending:
        memory = Memory.objects.create(
            user=batch.user,
            title=(ch.title or f"Imported story {ch.index}")[:255],
            body=ch.body,
            entry_state=Memory.EntryState.DRAFT,
            source_kind=Memory.SourceKind.OWNER,
            created_via=Memory.CREATED_VIA_IMPORT,
            import_batch=batch,
            import_chunk=ch.index,
            provenance_note=f"Imported from {batch.source_name} · {ch.source_ref}"[:255],
        )
        if run_discovery:
            try:
                discovery_svc.run_discovery(memory)   # exact same engine, proposals only
            except Exception:  # never let a discovery hiccup fail the import
                logger.warning("import: discovery failed for memory %s", memory.pk, exc_info=True)
        ch.status = ImportChunk.Status.IMPORTED
        ch.memory = memory
        ch.save(update_fields=["status", "memory"])
        memories.append(memory)

    batch.refresh_counts()
    return memories


# Display order + warm labels for the review queues shown after classification.
_QUEUE_ORDER = [
    ("story", "Stories", "Narrative memories — these run through Discovery."),
    ("journal_entry", "Journal entries", "Dated personal entries."),
    ("letter", "Letters", "Letters written to or by you."),
    ("fact", "Facts", "Concise facts — dates, names, details. These are not stories."),
    ("person", "People", "People described in this document."),
    ("relationship_alias", "Relationship aliases", "Words like “Dad” — who do they mean?"),
    ("place", "Places", "Places named in this document."),
    ("milestone", "Life milestones", "Marriages, births, moves — the big chapters."),
    ("timeline_event", "Timeline events", "Dated events that anchor your timeline."),
    ("quote", "Quotes", "Sayings and memorable lines."),
    ("artifact", "Artifacts", "Objects that carry meaning."),
    ("media_ref", "Media references", "Mentions of photos, video, or audio."),
    ("biography", "Biographies", "Longer accounts of a person's life."),
    ("description", "Descriptions", "Descriptive passages."),
    ("gedcom_person", "Genealogy — people", "Individuals from your family tree."),
    ("gedcom_family", "Genealogy — families", "Marriages and children from your family tree."),
    ("unknown", "Help Legacy understand", "A few things Legacy wasn't sure about. Tell it what they are and it'll remember — nothing here becomes a story until you do."),
]


def review_queues(batch):
    """Group a batch's chunks into ordered, labelled review queues by what each
    unit was classified as. The orchestrator's output — one upload, many queues."""
    from apps.legacy.models import ImportChunk

    by_kind = {}
    for ch in batch.chunks.all():
        by_kind.setdefault(ch.chunk_kind, []).append(ch)

    queues = []
    for kind, label, blurb in _QUEUE_ORDER:
        items = by_kind.get(kind)
        if not items:
            continue
        queues.append({
            "kind": kind,
            "label": label,
            "blurb": blurb,
            "items": items,
            "count": len(items),
            "pending": sum(1 for c in items if c.status == ImportChunk.Status.PENDING),
            "is_narrative": kind in {k.value for k in ImportChunk.NARRATIVE_KINDS},
        })
    return queues


def narrative_pending(batch):
    """How many narrative units are still waiting to be brought in as stories."""
    from apps.legacy.models import ImportChunk
    return batch.chunks.filter(
        status=ImportChunk.Status.PENDING,
        chunk_kind__in=list(ImportChunk.NARRATIVE_KINDS)).count()


def commit_genealogy(batch):
    """Commit a GEDCOM batch's structured people + families into Canonical Truth:
    Person records (with birth/death years) and spouse / parent-child Relationships.
    Deterministic, idempotent (dedupes people by name, links by triple). Returns
    (people_created, links_created). Genealogy — no Discovery."""
    from datetime import date
    from apps.legacy.models import ImportChunk, Person, Relationship

    def _d(iso):
        try:
            return date.fromisoformat(iso) if iso else None
        except (TypeError, ValueError):
            return None

    user = batch.user
    xref_to_person = {}
    people_created = 0

    # ONE Person per GEDCOM individual (identified by its xref) — NEVER merged by
    # name. Two different people named "James Robertson" stay two people; the user
    # merges true duplicates by hand. Merging by name is what created impossible
    # parent counts. Re-commit is idempotent via (source_batch, gedcom_xref).
    for ch in batch.chunks.filter(chunk_kind="gedcom_person"):
        d = ch.data or {}
        name = (d.get("name") or ch.title or "Unknown person").strip()
        xref = (d.get("xref") or "").strip()
        person = None
        if xref:
            person = Person.all_objects.filter(
                user=user, source_batch=batch, gedcom_xref=xref).first()
        if person is None:
            person = Person.objects.create(
                user=user, display_name=name[:200],
                birth_year=d.get("birth_year"), death_year=d.get("death_year"),
                birth_date=_d(d.get("birth_date")), death_date=_d(d.get("death_date")),
                source_batch=batch, gedcom_xref=xref[:40],
                created_via=Person.CREATED_VIA_IMPORT)
            people_created += 1
        else:
            fields = []
            for f in ("birth_year", "death_year"):
                if not getattr(person, f) and d.get(f):
                    setattr(person, f, d[f]); fields.append(f)
            for f in ("birth_date", "death_date"):
                if not getattr(person, f) and _d(d.get(f)):
                    setattr(person, f, _d(d[f])); fields.append(f)
            if fields:
                person.save(update_fields=fields + ["updated_at"])
        if xref:
            xref_to_person[xref] = person
        if ch.status != ImportChunk.Status.IMPORTED:
            ch.status = ImportChunk.Status.IMPORTED
            ch.save(update_fields=["status"])

    links_created = 0

    def _link(a, b, rtype, **extra):
        nonlocal links_created
        if not a or not b or a.pk == b.pk:
            return
        _, made = Relationship.objects.get_or_create(
            user=user, from_person=a, to_person=b, relationship_type=rtype,
            defaults=extra)
        if made:
            links_created += 1

    for ch in batch.chunks.filter(chunk_kind="gedcom_family"):
        d = ch.data or {}
        husb = xref_to_person.get(d.get("husb"))
        wife = xref_to_person.get(d.get("wife"))
        _link(husb, wife, "married to",
              started_year=d.get("marriage_year"), started_date=_d(d.get("marriage_date")))
        for x in (d.get("children") or []):
            child = xref_to_person.get(x)
            for parent in (husb, wife):
                _link(parent, child, "parent of")
        if ch.status != ImportChunk.Status.IMPORTED:
            ch.status = ImportChunk.Status.IMPORTED
            ch.save(update_fields=["status"])

    batch.refresh_counts()
    return people_created, links_created


def rebuild_genealogy(user):
    """Repair genealogy created by the old name-merging importer. Removes prior
    import-origin genealogy people that carry no stories (and their relationships),
    then re-commits every GEDCOM batch cleanly — one Person per individual, no
    name merging. People who have since gained stories are preserved. Re-binds the
    keeper afterwards. Returns (removed, people_created, links_created)."""
    from django.db.models import Count, Q
    from apps.legacy.models import ImportBatch, Person
    from apps.legacy.services.self_binding import bind_self, get_self_person

    self_p = get_self_person(user)
    self_name = self_p.display_name if self_p else None

    stale = (Person.all_objects.filter(user=user).annotate(_mc=Count("memories"))
             .filter(_mc=0)
             .filter(Q(source_batch__isnull=False) | Q(created_via=Person.CREATED_VIA_IMPORT)))
    removed = stale.count()
    stale.delete()   # cascades their relationships

    people_created = links_created = 0
    for batch in ImportBatch.all_objects.filter(user=user, source_type="gedcom"):
        # forget any stale per-chunk person links, then re-commit fresh
        p, l = commit_genealogy(batch)
        people_created += p
        links_created += l

    if self_name:
        again = Person.objects.filter(user=user, display_name__iexact=self_name).first()
        if again:
            bind_self(user, again)
    return removed, people_created, links_created


def validate_family_graph(user):
    """Diagnostic: return human-readable integrity problems in the relationship
    graph (e.g. more than two biological-style parents). Empty list = healthy."""
    from collections import defaultdict
    from apps.legacy.models import Relationship
    names, parents = {}, defaultdict(list)
    for r in (Relationship.objects.filter(user=user)
              .select_related("from_person", "to_person")):
        names[r.from_person_id] = r.from_person.display_name
        names[r.to_person_id] = r.to_person.display_name
        t = (r.relationship_type or "").lower()
        if "parent of" in t and not any(k in t for k in ("step", "adoptive", "guardian")):
            parents[r.to_person_id].append(r.from_person.display_name)
    issues = []
    for child_id, ps in parents.items():
        if len(ps) > 2:
            issues.append("%s has %d biological parents: %s"
                          % (names.get(child_id, "?"), len(ps), ", ".join(ps)))
    return issues


def batch_stats(batch):
    """Warm, human statistics for an import — reveals the richness being preserved."""
    from apps.legacy.models import MemoryDiscovery

    mem_ids = list(batch.memories.values_list("id", flat=True))
    d = MemoryDiscovery.objects.filter(memory_id__in=mem_ids).exclude(
        status=MemoryDiscovery.Status.REJECTED)

    def k(kind):
        return d.filter(kind=kind).count()

    people = list(d.filter(kind=MemoryDiscovery.Kind.PERSON))
    relationships = sum(1 for p in people if (p.detail or {}).get("relationship"))
    accepted_people = [p for p in people if p.status == MemoryDiscovery.Status.ACCEPTED]
    new_people = sum(1 for p in accepted_people if (p.detail or {}).get("is_new"))
    existing_matched = len(accepted_people) - new_people

    return {
        "stories_imported": batch.imported_count,
        "stories_total": batch.total_chunks,
        "people": len(people),
        "places": k(MemoryDiscovery.Kind.PLACE),
        "relationships": relationships,
        "quotes": k(MemoryDiscovery.Kind.QUOTE),
        "themes": k(MemoryDiscovery.Kind.THEME),
        "traditions": k(MemoryDiscovery.Kind.TRADITION),
        "artifacts": k(MemoryDiscovery.Kind.ARTIFACT),
        "events": k(MemoryDiscovery.Kind.EVENT),
        "media": k(MemoryDiscovery.Kind.MEDIA_REF),
        "values": k(MemoryDiscovery.Kind.VALUE),
        "new_people": new_people,
        "existing_matched": existing_matched,
    }
