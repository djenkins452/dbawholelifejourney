"""
ArtifactQueries — deterministic retrieval over uploaded MultimodalArtifacts.

The single, user-scoped query surface that turns "that receipt", "the MRI", "the
PDF I uploaded after my appointment", "bloodwork" into concrete artifacts. Content
search runs over the DETERMINISTIC extracted text/transcript (WLJ decoded it) plus
the filename and type — never an interpretation. The ArtifactDomainTruth provider
composes these into Truth-Surface entities; nothing else re-derives retrieval.
"""
from django.db.models import Q


class ArtifactQueries:
    """All methods are user-scoped (the query IS the ownership boundary)."""

    @staticmethod
    def _base(user):
        from apps.capture.models import MultimodalArtifact
        # Exclude dedup shadows / rejects — surface real, resolved-or-received artifacts.
        return (MultimodalArtifact.objects
                .filter(user=user)
                .exclude(status="duplicate")
                .exclude(status="rejected"))

    @staticmethod
    def recent(user, *, kind=None, limit=50):
        qs = ArtifactQueries._base(user)
        if kind:
            qs = qs.filter(kind=kind)
        return list(qs.order_by("-created_at")[:limit])

    @staticmethod
    def search(user, query, *, kind=None, since=None, limit=20):
        """Find artifacts whose extracted text / filename / type matches `query`.

        Deterministic keyword match (icontains) over decoded content + metadata —
        ordered newest first. `since` is a date/datetime lower bound.
        """
        qs = ArtifactQueries._base(user)
        if kind:
            qs = qs.filter(kind=kind)
        if since is not None:
            qs = qs.filter(created_at__gte=since)
        q = (query or "").strip()
        if q:
            qs = qs.filter(
                Q(extracted_text__icontains=q)
                | Q(original_filename__icontains=q)
                | Q(content_type__icontains=q)
                | Q(kind__iexact=q)
            )
        return list(qs.order_by("-created_at")[:limit])

    @staticmethod
    def by_id(user, artifact_id):
        return ArtifactQueries._base(user).filter(id=artifact_id).first()

    @staticmethod
    def last_uploaded(user, *, query=None, kind=None):
        """The most recent artifact (optionally matching a content query / kind).
        Answers 'when did I last upload bloodwork?'."""
        if query:
            hits = ArtifactQueries.search(user, query, kind=kind, limit=1)
            return hits[0] if hits else None
        hits = ArtifactQueries.recent(user, kind=kind, limit=1)
        return hits[0] if hits else None

    @staticmethod
    def counts_by_kind(user):
        from django.db.models import Count
        rows = (ArtifactQueries._base(user)
                .values("kind")
                .annotate(n=Count("id")))
        return {r["kind"] or "other": r["n"] for r in rows}
