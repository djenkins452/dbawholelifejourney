"""
ArtifactDomainTruth — uploaded artifacts as a first-class Truth Surface.

Every file a user uploads (MultimodalArtifact — PDF, image, audio, video, …) is
deterministic truth with provenance, not a fleeting conversation attachment. This
provider makes them RETRIEVABLE by the Chief of Staff exactly like any other
domain truth: "what did my MRI say", "show me the receipt from last month", "when
did I last upload bloodwork". WLJ owns identity/storage/indexing/retrieval/
provenance; the model reasons over what is returned.

Owns NO new retrieval logic — composes `ArtifactQueries` into `CompleteEntity`s.
Content shown is the DETERMINISTICALLY extracted text/transcript (never an
interpretation).
"""
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT, MISSING

# Bound the readable content returned per artifact so a retrieval turn stays sane
# (the full text lives on the artifact).
_CONTENT_CHARS = 20_000
_KIND_TYPES = ("document", "image", "audio", "video")


@register_domain_truth
class ArtifactDomainTruth(DomainTruth):
    domain = "artifacts"
    current_metrics = ("recent_uploads",)
    history_metrics = ()
    # 'artifact' = every upload; the kind aliases let the model list one class.
    entity_types = ("artifact",) + _KIND_TYPES

    def describe(self, entity_type=None):
        from apps.capture.services.artifact_queries import ArtifactQueries
        et = (entity_type or "").strip().lower()
        kind = et if et in _KIND_TYPES else None
        rows = ArtifactQueries.recent(self.user, kind=kind, limit=50)
        return [self._artifact_entity(a) for a in rows]

    def describe_one(self, name):
        from apps.capture.services.artifact_queries import ArtifactQueries
        q = (name or "").strip()
        if not q:
            return None
        hits = ArtifactQueries.search(self.user, q, limit=1)
        return self._artifact_entity(hits[0]) if hits else None

    def current(self, metric):
        from apps.core.truth.current import CurrentTruth
        if metric != "recent_uploads":
            return CurrentTruth.absent(self.domain, metric, MISSING,
                                       source="artifact_queries",
                                       reason="unknown metric")
        from apps.capture.services.artifact_queries import ArtifactQueries
        counts = ArtifactQueries.counts_by_kind(self.user)
        total = sum(counts.values())
        if total == 0:
            return CurrentTruth.absent(self.domain, metric, MISSING,
                                       source="artifact_queries",
                                       reason="no uploaded artifacts")
        last = ArtifactQueries.last_uploaded(self.user)
        return CurrentTruth.found(
            self.domain, metric,
            value=total,
            unit="artifacts",
            source="artifact_queries",
            freshness=CURRENT,
            detail={
                "by_kind": counts,
                "last_uploaded_at": last.created_at.isoformat() if last else None,
                "last_uploaded_kind": (last.kind if last else None),
            },
        )

    def _artifact_entity(self, a):
        date = a.created_at.date().isoformat()
        identity = a.original_filename or f"{(a.kind or 'file').title()} uploaded {date}"
        # Readable content = the deterministically extracted text/transcript.
        content = None
        if a.has_perception:
            content = (a.extracted_text or "")[:_CONTENT_CHARS] or None
        perception = None
        if a.perception_pending:
            perception = "processing"
        elif a.perception_status == a.PERCEPTION_UNSUPPORTED:
            perception = "unreadable"

        provenance = {}
        if a.resolved_intent:
            provenance = {
                "resolved_intent": a.resolved_intent,
                "object_type": a.resolved_object_type or None,
                "object_id": a.resolved_object_id,
            }

        return CompleteEntity(
            kind=a.kind or "artifact",
            identity=identity,
            definition={
                "artifact_id": a.id,
                "filename": a.original_filename or None,
                "content_type": a.content_type,
                "kind": a.kind or None,
                "page_count": a.page_count,
                "byte_size": a.byte_size,
            },
            status=a.status,
            standing={
                "uploaded_at": a.created_at.isoformat(),
                "uploaded_date": date,
                "durably_stored": a.is_durably_stored,
                "perception": perception,
            },
            performance={
                "readable": bool(content),
                "content": content,
            },
            extensions={"provenance": provenance} if provenance else {},
            freshness=CURRENT,
        )
