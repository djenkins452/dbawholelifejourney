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


def create_batch(user, source_name, source_type, raw_text):
    """Parse a document into an ImportBatch + pending ImportChunks (imports nothing)."""
    from apps.legacy.models import ImportBatch, ImportChunk

    adapter = get_adapter(source_type)
    segments = adapter(raw_text or "")
    chunks = chunk(segments)

    batch = ImportBatch.objects.create(
        user=user,
        source_name=(source_name or "Untitled document")[:255],
        source_type=source_type,
        total_chunks=len(chunks),
        import_status=ImportBatch.Status.PARSED,
        created_via=ImportBatch.CREATED_VIA_IMPORT,
    )
    ImportChunk.objects.bulk_create([
        ImportChunk(batch=batch, index=c["index"], title=c["title"][:255],
                    body=c["body"], source_ref=c["source_ref"][:120])
        for c in chunks
    ])
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
        qs = qs.filter(index__in=[int(i) for i in indices])
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
