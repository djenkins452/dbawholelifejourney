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


def _iso_to_date(iso):
    from datetime import date
    try:
        return date.fromisoformat(iso) if iso else None
    except (TypeError, ValueError):
        return None


def backfill_gedcom_dates(user, progress=None):
    """Fill missing full dates (birth/death) onto already-committed genealogy
    people, recovering them from each import chunk's structured data or body text.
    Non-destructive; only sets a date that's currently empty. Returns count updated.
    `progress(n)` (optional) is called every 100 chunks with the running count.

    O(N): the user's people are loaded ONCE into in-memory lookup maps (by
    xref-key and by normalized name), so there is no per-chunk query and no
    case-insensitive table scan; changed people are written with a single
    bulk_update. Safe on a 1,500-person tree."""
    from apps.legacy.models import ImportBatch, Person
    from apps.legacy.services.gedcom_parser import dates_from_body

    people = list(Person.all_objects.filter(user=user).only(
        "pk", "display_name", "gedcom_xref", "source_batch_id",
        "birth_date", "death_date", "updated_at"))
    by_name, by_key = {}, {}
    for p in people:
        by_name.setdefault((p.display_name or "").strip().lower(), p)
        if p.gedcom_xref:
            by_key[(p.source_batch_id, p.gedcom_xref)] = p

    changed = {}   # pk -> person (deduped; a person may match several chunks)
    seen = 0
    for batch in ImportBatch.all_objects.filter(user=user, source_type="gedcom"):
        for ch in batch.chunks.filter(chunk_kind="gedcom_person").only(
                "data", "body", "chunk_kind", "batch_id"):
            seen += 1
            if progress and seen % 100 == 0:
                progress(seen)
            d = ch.data or {}
            body_b, body_d = dates_from_body(ch.body)
            b_iso = d.get("birth_date") or body_b
            de_iso = d.get("death_date") or body_d
            if not b_iso and not de_iso:
                continue
            person = by_key.get((batch.pk, d.get("xref"))) if d.get("xref") else None
            if person is None:
                person = by_name.get((d.get("name") or ch.title or "").strip().lower())
            if person is None:
                continue
            hit = False
            if person.birth_date is None and _iso_to_date(b_iso):
                person.birth_date = _iso_to_date(b_iso); hit = True
            if person.death_date is None and _iso_to_date(de_iso):
                person.death_date = _iso_to_date(de_iso); hit = True
            if hit:
                changed[person.pk] = person

    if changed:
        Person.all_objects.bulk_update(
            list(changed.values()), ["birth_date", "death_date"], batch_size=500)
    return len(changed)


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

    # Completeness/preservation report — proves nothing in the source was
    # silently discarded, and surfaces what Legacy can't store canonically yet.
    coverage = gedcom_parser.analyze_coverage(chunks)

    batch = ImportBatch.objects.create(
        user=user,
        source_name=(source_name or "Untitled document")[:255],
        source_type=source_type,
        total_chunks=len(chunks),
        import_status=ImportBatch.Status.PARSED,
        created_via=ImportBatch.CREATED_VIA_IMPORT,
        coverage=coverage,
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


def _couple_bond(family_data):
    """The couple's marriage evidence for a gedcom_family chunk as (couple_type,
    status): ('married'/'former', 'known') with real evidence, (None,
    'needs_clarification') for a multi-child family unit with no marriage event (a
    QUESTION, not a marriage), or (None, None). New chunks carry `marriage_status`
    from the parser; legacy chunks are inferred — marriage year/date/place ⇒ known
    married; otherwise >= 2 shared children ⇒ needs_clarification."""
    if "marriage_status" in family_data:
        return family_data.get("couple_type"), family_data.get("marriage_status")
    if family_data.get("marriage_year") or family_data.get("marriage_date") \
            or family_data.get("marriage_place"):
        return "married", "known"
    if len(family_data.get("children") or []) >= 2:
        return None, "needs_clarification"
    return None, None


_PARENTISH = ("parent", "father", "mother", "guardian")


def _is_parentish(t):
    t = (t or "").lower()
    return any(k in t for k in _PARENTISH) and "grand" not in t


def _is_generic_parent(t):
    """A non-specific parent bond that a refresh MAY refine: blank, 'parent of', or
    'child of'. A specific type (biological/step/adoptive/foster/guardian, or gendered
    father/mother) is never downgraded."""
    return (t or "").strip().lower() in ("", "parent", "parent of", "child of")


def _pedi_base(value):
    """Normalize a pedigree/relationship qualifier to a base kind. '' when unknown
    (the caller defaults to biological — a plain HUSB/WIFE→CHIL link)."""
    v = (value or "").lower()
    if "adopt" in v:
        return "adopted"
    if "foster" in v:
        return "foster"
    if "step" in v:
        return "step"
    if "guardian" in v or "ward" in v:
        return "guardian"
    if "birth" in v or "biolog" in v or "natural" in v:
        return "birth"
    return ""


def _parent_type(sex, base):
    """The canonical parent relationship_type from (parent sex, pedigree base).
    Male→father, Female→mother, unknown→neutral. This is how the importer produces
    'biological father of' / 'stepmother of' / 'adoptive mother of' automatically."""
    s = (sex or "").upper()
    m, f = s.startswith("M"), s.startswith("F")
    if base == "adopted":
        return "adoptive father of" if m else "adoptive mother of" if f else "adoptive parent of"
    if base == "foster":
        return "foster parent of"
    if base == "guardian":
        return "guardian of"
    if base == "step":
        return "stepfather of" if m else "stepmother of" if f else "step-parent of"
    return "biological father of" if m else "biological mother of" if f else "parent of"


# NOTE: There is deliberately NO step-parent INFERENCE. A step-parent is created ONLY
# from explicit evidence — a child whose pedigree to that parent is marked step
# (_FREL/_MREL/PEDI), handled by the pedigree path in `_parent_type`. Marriage does NOT
# imply a step-parent: a spouse of a parent is not automatically a step-parent (that
# made Danny have seven parents). Where the source can't prove it, the Clarification
# Engine ASKS the user (services/clarification.py :: StepParentClarification). Legacy
# preserves evidence and asks; it never invents relationships.


def refine_existing_family_types(user):
    """Bring ALREADY-imported genealogy up to the evidence-based standard WITHOUT a
    re-import: backfill Person.sex from the stored import chunks and upgrade generic
    'parent of' bonds to biological father/mother by that sex. Evidence only — no
    step-parent inference. Idempotent. Returns (sex_set, parents_upgraded)."""
    from apps.legacy.models import ImportChunk, Person, Relationship

    sex_by_person = {}
    for ch in ImportChunk.objects.filter(batch__user=user, chunk_kind="gedcom_person"):
        d = ch.data or {}
        xref = (d.get("xref") or "").strip()
        s = (d.get("sex") or "")[:1].upper()
        if xref and s in ("M", "F"):
            sex_by_person[(ch.batch_id, xref)] = s

    sex_set = 0
    for p in (Person.all_objects.filter(user=user, source_batch__isnull=False)
              .exclude(gedcom_xref="")):
        if p.sex:
            continue
        s = sex_by_person.get((p.source_batch_id, p.gedcom_xref))
        if s:
            p.sex = s
            p.save(update_fields=["sex", "updated_at"])
            sex_set += 1

    upgraded = 0
    for r in (Relationship.objects.filter(user=user, relationship_type="parent of")
              .select_related("from_person")):
        s = (r.from_person.sex or "").upper()
        rtype = ("biological father of" if s.startswith("M")
                 else "biological mother of" if s.startswith("F") else "")
        if rtype:
            r.relationship_type = rtype
            r.save(update_fields=["relationship_type", "relationship_category", "updated_at"])
            upgraded += 1

    return sex_set, upgraded


def commit_genealogy(batch, chunks_from=None):
    """Commit a GEDCOM batch's structured people + families into Canonical Truth:
    Person records (with birth/death years) and spouse / parent-child Relationships.
    Deterministic, idempotent (people keyed on (lineage batch, gedcom_xref); links
    upsert). Returns (people_created, links_created). Genealogy — no Discovery.

    `chunks_from` powers Smart Refresh: read the chunks from a NEWER upload while
    keying people to the ORIGINAL lineage `batch`, so a refresh SYNCHRONIZES the
    existing tree (matched xrefs update, new xrefs join the lineage) instead of
    duplicating it."""
    from django.db.models import Q

    from apps.legacy.models import ImportChunk, Person, Relationship
    from apps.legacy.services.gedcom_parser import dates_from_body
    from apps.legacy.services.preservation import preserve_facts

    _d = _iso_to_date
    user = batch.user
    src = chunks_from or batch    # where the chunks are read FROM (newer file on refresh)
    xref_to_person = {}
    pedi_by_xref = {}     # child xref -> {family xref: pedigree} (standard PEDI)
    people_created = 0

    # ONE Person per GEDCOM individual (identified by its xref) — NEVER merged by
    # name. Two different people named "James Robertson" stay two people; the user
    # merges true duplicates by hand. Merging by name is what created impossible
    # parent counts. Re-commit is idempotent via (source_batch, gedcom_xref).
    for ch in src.chunks.filter(chunk_kind="gedcom_person"):
        d = ch.data or {}
        name = (d.get("name") or ch.title or "Unknown person").strip()
        xref = (d.get("xref") or "").strip()
        # Full dates from the structured payload, or recovered from the body text
        # (so people imported before dates were captured still get them on re-commit).
        body_b, body_d = dates_from_body(ch.body)
        birth_iso = d.get("birth_date") or body_b
        death_iso = d.get("death_date") or body_d
        person = None
        if xref:
            person = Person.all_objects.filter(
                user=user, source_batch=batch, gedcom_xref=xref).first()
        sex = (d.get("sex") or "")[:1].upper()
        if person is None:
            person = Person.objects.create(
                user=user, display_name=name[:200], sex=sex,
                birth_year=d.get("birth_year"), death_year=d.get("death_year"),
                birth_date=_d(birth_iso), death_date=_d(death_iso),
                source_batch=batch, gedcom_xref=xref[:40],
                created_via=Person.CREATED_VIA_IMPORT)
            people_created += 1
        else:
            fields = []
            for f in ("birth_year", "death_year"):
                if not getattr(person, f) and d.get(f):
                    setattr(person, f, d[f]); fields.append(f)
            if not person.birth_date and _d(birth_iso):
                person.birth_date = _d(birth_iso); fields.append("birth_date")
            if not person.death_date and _d(death_iso):
                person.death_date = _d(death_iso); fields.append("death_date")
            if sex and person.sex != sex:
                person.sex = sex; fields.append("sex")
            if fields:
                person.save(update_fields=fields + ["updated_at"])
        if xref:
            xref_to_person[xref] = person
            pedi_by_xref[xref] = d.get("famc_pedi") or {}
        # PERMANENT preservation — every fact Canonical Truth can't model yet is
        # stored durably against this Person, never left only inside the session.
        preserve_facts(user, batch, person, name, (d.get("facts") or []))
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

    def _couple_link(a, b, rtype, **extra):
        """Link a couple, but only if NO couple bond already exists between them
        (either direction, any couple type). Prevents a refresh from stacking a second
        'married to' on top of a user's 'former spouse of', and respects user edits."""
        nonlocal links_created
        if not a or not b or a.pk == b.pk:
            return
        for r in Relationship.objects.filter(user=user).filter(
                Q(from_person=a, to_person=b) | Q(from_person=b, to_person=a)):
            if any(k in (r.relationship_type or "").lower()
                   for k in ("married", "spouse", "partner", "husband", "wife")):
                return                        # a couple bond already exists — leave it
        Relationship.objects.create(user=user, from_person=a, to_person=b,
                                    relationship_type=rtype, **extra)
        links_created += 1

    def _parent_link(parent, child, rtype):
        """Create or REFINE a parent→child bond. Only ever REFINES a generic/blank
        type ('parent of' → 'biological father of'); NEVER downgrades a specific type
        and NEVER touches a user-edited relationship. This is what lets a refresh from
        a poorer source improve Canonical Truth without ever eroding it."""
        nonlocal links_created
        if not parent or not child or parent.pk == child.pk:
            return
        existing = None
        for r in Relationship.objects.filter(user=user, from_person=parent, to_person=child):
            if _is_parentish(r.relationship_type):
                existing = r
                break
        if existing:
            if (not existing.user_edited and _is_generic_parent(existing.relationship_type)
                    and not _is_generic_parent(rtype)):
                existing.relationship_type = rtype
                existing.save(update_fields=["relationship_type", "relationship_category",
                                             "updated_at"])
        else:
            Relationship.objects.create(user=user, from_person=parent, to_person=child,
                                        relationship_type=rtype)
            links_created += 1

    for ch in src.chunks.filter(chunk_kind="gedcom_family"):
        d = ch.data or {}
        fam_xref = d.get("xref") or ""
        husb = xref_to_person.get(d.get("husb"))
        wife = xref_to_person.get(d.get("wife"))
        # A FAM record is a family UNIT — it does NOT imply marriage. Only assert a
        # spouse relationship on KNOWN evidence (a MARR/DIV/… event). A family unit
        # with no marriage event is NEVER inferred as married — it becomes a question
        # the clarification engine asks the user (see services/clarification.py).
        # Either way the couple stay linked through their children.
        ctype, status = _couple_bond(d)
        if ctype and status == "known":
            _couple_link(husb, wife, "former spouse of" if ctype == "former" else "married to",
                         started_year=d.get("marriage_year"), started_date=_d(d.get("marriage_date")))
        # Parents are typed from the evidence the GEDCOM already carries — the parent's
        # SEX (father/mother) and the pedigree qualifier (_FREL/_MREL per parent, or the
        # child's PEDI for this family). Default is biological. Never a generic "Parent"
        # when the source knows better.
        child_rels = d.get("child_rels") or {}
        for x in (d.get("children") or []):
            child = xref_to_person.get(x)
            if not child:
                continue
            cr = child_rels.get(x) or {}
            child_pedi = (pedi_by_xref.get(x) or {}).get(fam_xref, "")
            for parent, slot in ((husb, "father"), (wife, "mother")):
                if not parent:
                    continue
                base = _pedi_base(cr.get(slot)) or _pedi_base(child_pedi) or "birth"
                _parent_link(parent, child, _parent_type(parent.sex, base))
        # Family-level facts (e.g. divorce) preserved too — nothing left behind.
        preserve_facts(user, batch, None, ch.title, (d.get("facts") or []))
        if ch.status != ImportChunk.Status.IMPORTED:
            ch.status = ImportChunk.Status.IMPORTED
            ch.save(update_fields=["status"])

    # NO step-parent inference. Step-parents come ONLY from explicit pedigree evidence
    # (handled above) or from the user resolving a StepParent clarification. A spouse of
    # a parent is NOT assumed to be a step-parent.

    batch.refresh_counts()
    return people_created, links_created


def _family_persons(batch, d):
    """Resolve the husband/wife Person objects for a committed family chunk."""
    from apps.legacy.models import Person
    user = batch.user
    hx = (d.get("husb") or "").strip()
    wx = (d.get("wife") or "").strip()
    hp = Person.objects.filter(user=user, source_batch=batch, gedcom_xref=hx).first() if hx else None
    wp = Person.objects.filter(user=user, source_batch=batch, gedcom_xref=wx).first() if wx else None
    return hp, wp


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
