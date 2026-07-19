"""
Current Context PAGE-SUMMARY providers for the Artifact Library pages.

Registered at app-ready (see CaptureConfig.ready). Each is user-scoped and
request-path-safe, returning the uniform {title, content, kind} the CoS consumes
as Current Context — the SAME deterministic truth the page renders. Facts only.
"""
from apps.core.current_context import register_page_summary


@register_page_summary("artifacts.library")
def artifact_library_summary(user, params):
    """The uploads library/gallery. Reflects the current search/filter so the CoS
    knows exactly what the user is looking at."""
    from apps.capture.services.artifact_queries import ArtifactQueries

    params = params or {}
    q = (params.get("q") or "").strip()
    kind = (params.get("kind") or "").strip().lower()
    kind = kind if kind in ("image", "document", "audio", "video") else None

    counts = ArtifactQueries.counts_by_kind(user)
    total = sum(counts.values())
    if total == 0:
        return {"title": "Your uploads", "kind": "uploads library",
                "content": "The uploads library — nothing uploaded yet."}

    if q or kind:
        rows = ArtifactQueries.search(user, q, kind=kind, limit=20)
        scope = []
        if q:
            scope.append(f'matching "{q}"')
        if kind:
            scope.append(f"of type {kind}")
        head = f"Uploads library, filtered ({', '.join(scope)}): {len(rows)} shown."
    else:
        rows = ArtifactQueries.recent(user, limit=20)
        by = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()))
        head = f"Uploads library — {total} files ({by}). Most recent first."

    lines = [head]
    for a in rows[:12]:
        lines.append(f"- {_label(a)} ({a.kind or 'file'}, uploaded {a.created_at.date().isoformat()})")
    return {"title": "Your uploads", "kind": "uploads library", "content": "\n".join(lines)}


@register_page_summary("artifacts.detail")
def artifact_detail_summary(user, params):
    """One uploaded file — the object the user is looking at."""
    from apps.capture.services.artifact_queries import ArtifactQueries

    aid = (params or {}).get("id")
    a = ArtifactQueries.by_id(user, aid) if aid else None
    if a is None:
        return None

    lines = [
        f"Viewing an uploaded {a.kind or 'file'}: {_label(a)}.",
        f"Type: {a.content_type}. Uploaded: {a.created_at.date().isoformat()}.",
    ]
    if a.page_count:
        lines.append(f"Pages/frames: {a.page_count}.")
    if a.perception_pending:
        lines.append("WLJ is still reading this file (processing).")
    elif a.has_perception and a.extracted_text:
        excerpt = a.extracted_text[:600]
        lines.append(f"Extracted content (deterministic):\n{excerpt}")
    elif a.perception_status == a.PERCEPTION_UNSUPPORTED:
        lines.append("This file could not be read as text (e.g. a scan or silent audio).")
    if a.resolved_intent:
        lines.append(f"Produced a record via: {a.resolved_intent}.")
    if a.associations:
        lines.append(f"Linked to: {', '.join(a.associations)}.")
    return {"title": _label(a), "kind": "uploaded file", "content": "\n".join(lines)}


def _label(a):
    return a.original_filename or f"{(a.kind or 'file').title()} from {a.created_at.date().isoformat()}"
