"""
Whole Life Journey - Notes Service Layer

Project: Whole Life Journey
Path: apps/notes/services.py
Purpose: CoS-ready retrieval API for searching, fetching, and citing notes.

This module provides a stable, framework-agnostic interface for querying
notes. It is designed for use by the Chief of Staff (CoS) intelligence layer,
internal callers, and future API endpoints. It has no HttpRequest dependency.
"""

import logging
import re
import string

from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.search import SearchHeadline, SearchQuery, SearchRank
from django.db import models
from django.db.models import F, Prefetch

from .models import Note, NoteAttachment
from .utils import resolve_entity_url

logger = logging.getLogger(__name__)


def _tokenize(text):
    """
    Tokenize text for match-source labeling.

    Lowercase, split on whitespace, strip punctuation, drop tokens < 2 chars.
    """
    if not text:
        return set()
    translator = str.maketrans("", "", string.punctuation)
    return {
        tok
        for tok in text.lower().translate(translator).split()
        if len(tok) >= 2
    }


def _compute_matched_in(query_tokens, note):
    """
    Determine which fields the query matched against.

    Returns a list of field names: "title", "body", "tags", "attachments".
    """
    if not query_tokens:
        return []

    matched_in = []
    fields = [
        ("title", note.title or ""),
        ("body", note.body or ""),
        ("tags", note.tags_text or ""),
        ("attachments", note.attachments_text or ""),
    ]
    for field_name, field_value in fields:
        field_tokens = _tokenize(field_value)
        if query_tokens & field_tokens:
            matched_in.append(field_name)
    return matched_in


def _build_attachment_block(att):
    """Build a structured attachment dict from a NoteAttachment instance."""
    ct = att.content_type
    ct_label = f"{ct.app_label}.{ct.model}"
    display = att.attachment_display()

    # Resolve URL best-effort
    url = None
    try:
        entity = att.attached_entity
        url = resolve_entity_url(entity)
    except Exception:
        pass

    return {
        "content_type": ct_label,
        "object_id": att.object_id,
        "display": display,
        "url": url,
    }


def _build_citation_block(note, *, query=None, query_tokens=None, headline=None, rank=None):
    """
    Build a citation block dict from a Note instance.

    The note must have been fetched with prefetched tags and attachments
    to avoid N+1 queries.
    """
    # Use prefetched tags (avoid extra query)
    tag_names = [t.name for t in note.tags.all()]

    # Use prefetched attachments
    attachments_list = []
    prefetched_attachments = note.attachments.all()
    for att in prefetched_attachments:
        attachments_list.append(_build_attachment_block(att))

    matched_in = _compute_matched_in(query_tokens, note) if query_tokens else []

    return {
        "note_id": note.pk,
        "display_title": note.display_title,
        "body_preview": note.body_preview,
        "body": note.body,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
        "is_pinned": note.is_pinned,
        "color": note.color,
        "tag_names": tag_names,
        "attachment_count": len(attachments_list),
        "attachments": attachments_list,
        "url": note.get_absolute_url(),
        "match": {
            "query": query or "",
            "matched_in": matched_in,
            "headline": headline or "",
            "rank": rank,
        },
    }


def _base_queryset(user):
    """
    Return the base Note queryset for a user with standard prefetches.

    Excludes soft-deleted notes. Prefetches tags and attachments to avoid N+1.
    """
    return (
        Note.objects.filter(user=user)
        .prefetch_related(
            "tags",
            Prefetch(
                "attachments",
                queryset=NoteAttachment.objects.select_related("content_type"),
            ),
        )
    )


def search_notes(
    *,
    user,
    query=None,
    tag_ids=None,
    color=None,
    pinned=None,
    attached_only=None,
    attached_content_types=None,
    date_from=None,
    date_to=None,
    limit=25,
    offset=0,
):
    """
    Search and filter notes for a user. Returns structured citation blocks.

    Args:
        user: The requesting user (ownership enforced).
        query: Full-text search string (websearch syntax supported).
        tag_ids: Filter to notes with any of these tag IDs.
        color: Filter to a specific color.
        pinned: If True, only pinned notes; if False, only unpinned.
        attached_only: If True, only notes with at least one attachment.
        attached_content_types: Filter to notes attached to specific model types
            (list of "app_label.model" strings).
        date_from: Only notes created on or after this date.
        date_to: Only notes created on or before this date.
        limit: Max results to return (default 25).
        offset: Pagination offset (default 0).

    Returns:
        dict with "count" (int) and "results" (list of citation_block dicts).
    """
    queryset = _base_queryset(user)

    # Filters
    if tag_ids:
        queryset = queryset.filter(tags__id__in=tag_ids)

    if color:
        queryset = queryset.filter(color=color)

    if pinned is not None:
        queryset = queryset.filter(is_pinned=pinned)

    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)

    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    if attached_only:
        queryset = queryset.filter(attachments__isnull=False)

    if attached_content_types:
        ct_filters = []
        for ct_str in attached_content_types:
            parts = ct_str.split(".")
            if len(parts) == 2:
                ct_filters.append(
                    ContentType.objects.filter(
                        app_label=parts[0], model=parts[1]
                    ).values_list("pk", flat=True)
                )
        if ct_filters:
            from functools import reduce
            from operator import or_

            from django.db.models import Q

            ct_q = reduce(or_, [Q(attachments__content_type__in=ct_qs) for ct_qs in ct_filters])
            queryset = queryset.filter(ct_q)

    # Full-text search
    query_str = (query or "").strip()
    query_tokens = _tokenize(query_str) if query_str else None
    headline_field = None

    if query_str:
        search_query = SearchQuery(query_str, search_type="websearch")
        queryset = (
            queryset.filter(search_vector=search_query)
            .annotate(
                rank=SearchRank(F("search_vector"), search_query),
                headline=SearchHeadline(
                    "body",
                    search_query,
                    start_sel="<mark>",
                    stop_sel="</mark>",
                    max_words=35,
                    min_words=15,
                ),
            )
            .order_by("-rank", "-is_pinned", "-updated_at")
        )
        headline_field = "headline"
    else:
        queryset = queryset.order_by("-is_pinned", "-updated_at")

    queryset = queryset.distinct()

    # Count before slicing
    total_count = queryset.count()

    # Paginate
    results_qs = queryset[offset : offset + limit]

    # Build citation blocks
    results = []
    for note in results_qs:
        headline_val = getattr(note, headline_field, "") if headline_field else ""
        rank_val = getattr(note, "rank", None)
        results.append(
            _build_citation_block(
                note,
                query=query_str,
                query_tokens=query_tokens,
                headline=str(headline_val) if headline_val else "",
                rank=float(rank_val) if rank_val is not None else None,
            )
        )

    return {
        "count": total_count,
        "results": results,
    }


def get_note_detail(*, user, note_id):
    """
    Fetch a single note with full detail as a citation block.

    Enforces user isolation and excludes soft-deleted notes.

    Args:
        user: The requesting user.
        note_id: The primary key of the note.

    Returns:
        A citation_block dict, or None if note not found / not owned.
    """
    try:
        note = _base_queryset(user).get(pk=note_id)
    except Note.DoesNotExist:
        return None

    return _build_citation_block(note)


def get_related_notes_for_entity(
    *, user, content_type, object_id, limit=50, use_cos_ranking=False
):
    """
    Fetch notes attached to a specific entity.

    Args:
        user: The requesting user (ownership enforced).
        content_type: String in "app_label.model" format (e.g., "life.task").
        object_id: The primary key of the entity.
        limit: Max results (default 50).
        use_cos_ranking: If True, apply memory intelligence scoring and
            include combined_score + reasons in each result.

    Returns:
        List of citation_block dicts (with scoring fields if use_cos_ranking).
    """
    parts = content_type.split(".")
    if len(parts) != 2:
        return []

    try:
        ct = ContentType.objects.get(app_label=parts[0], model=parts[1])
    except ContentType.DoesNotExist:
        return []

    note_ids = (
        NoteAttachment.objects.filter(content_type=ct, object_id=object_id)
        .values_list("note_id", flat=True)
    )

    queryset = (
        _base_queryset(user)
        .filter(pk__in=note_ids)
        .order_by("-is_pinned", "-updated_at")
    )[:limit]

    if not use_cos_ranking:
        return [_build_citation_block(note) for note in queryset]

    # CoS ranking: score each note with entity context
    from .memory_scoring import score_note

    results = []
    notes_list = list(queryset)
    for note in notes_list:
        block = _build_citation_block(note)
        att_entity_ids = _get_note_attachment_entity_ids(note)
        scoring = score_note(
            fts_rank=0,
            max_fts_rank=0,
            updated_at=note.updated_at,
            is_pinned=note.is_pinned,
            note_attachment_entity_ids=att_entity_ids,
            scoped_content_type_id=ct.pk,
            scoped_object_id=object_id,
            note_tag_names=[t.name for t in note.tags.all()],
            query_tags=[],
        )
        block["combined_score"] = scoring["combined_score"]
        block["reasons"] = scoring["reasons"]
        results.append(block)

    # Sort by combined_score descending
    results.sort(key=lambda r: r["combined_score"], reverse=True)
    return results


def _get_note_attachment_entity_ids(note):
    """
    Get set of (content_type_id, object_id) tuples from a note's prefetched attachments.
    """
    return {
        (att.content_type_id, att.object_id) for att in note.attachments.all()
    }


# ---------------------------------------------------------------------------
# CoS Memory Intelligence search (Phase 4C)
# ---------------------------------------------------------------------------

_COS_CANDIDATE_POOL = 50  # Max candidates fetched from FTS before re-ranking


def search_notes_cos(
    user,
    query,
    *,
    limit=10,
    content_type=None,
    object_id=None,
    tags=None,
    include_deleted=False,
):
    """
    CoS-focused note search with memory intelligence ranking.

    Runs full-text search to get candidates, then re-ranks using the
    memory_scoring module. Returns enriched results with combined_score
    and explainability reasons.

    Args:
        user: The requesting user.
        query: Search string (may be blank for pinned+recent fallback).
        limit: Max results to return (default 10).
        content_type: Optional entity scope, "app_label.model" format.
        object_id: Optional entity PK (requires content_type).
        tags: Optional list of tag name strings for overlap boosting.
        include_deleted: If True, include soft-deleted notes.

    Returns:
        dict with "query", "scope", "results" list.
    """
    from .memory_scoring import score_fallback_note, score_note

    query_str = (query or "").strip()
    scope = {}
    scoped_ct_id = None
    scoped_object_id = None

    # Resolve entity scope
    if content_type:
        scope["content_type"] = content_type
        parts = content_type.split(".")
        if len(parts) == 2:
            try:
                ct = ContentType.objects.get(app_label=parts[0], model=parts[1])
                scoped_ct_id = ct.pk
                if object_id is not None:
                    scoped_object_id = object_id
                    scope["object_id"] = object_id
            except ContentType.DoesNotExist:
                pass

    if tags:
        scope["tags"] = tags

    # Base queryset
    if include_deleted:
        base_qs = (
            Note.all_objects.filter(user=user)
            .prefetch_related(
                "tags",
                Prefetch(
                    "attachments",
                    queryset=NoteAttachment.objects.select_related("content_type"),
                ),
            )
        )
    else:
        base_qs = _base_queryset(user)

    # --- Blank query: return pinned + recent with fallback reasons ---
    if not query_str:
        return _cos_fallback_results(
            base_qs, limit=limit, scope=scope, query_str=""
        )

    # --- FTS search: get candidate pool ---
    search_query = SearchQuery(query_str, search_type="websearch")
    candidates_qs = (
        base_qs.filter(search_vector=search_query)
        .annotate(
            rank=SearchRank(F("search_vector"), search_query),
            headline=SearchHeadline(
                "body",
                search_query,
                start_sel="<mark>",
                stop_sel="</mark>",
                max_words=35,
                min_words=15,
            ),
        )
        .order_by("-rank")
    )

    # Entity scope filter: boost attached notes but also include non-attached
    if scoped_ct_id and scoped_object_id:
        # Include all candidates (entity scoring handles boosting)
        pass

    candidates = list(candidates_qs[:_COS_CANDIDATE_POOL])

    # --- No FTS matches: fallback to pinned + recent ---
    if not candidates:
        return _cos_fallback_results(
            base_qs, limit=limit, scope=scope, query_str=query_str,
            is_fallback=True,
        )

    # --- Score and re-rank candidates ---
    max_fts_rank = max(
        (getattr(c, "rank", 0) or 0 for c in candidates), default=0
    )

    query_tokens = _tokenize(query_str)
    scored_results = []

    for note in candidates:
        fts_rank = float(getattr(note, "rank", 0) or 0)
        headline_val = str(getattr(note, "headline", "") or "")
        tag_names = [t.name for t in note.tags.all()]
        att_entity_ids = _get_note_attachment_entity_ids(note)

        scoring = score_note(
            fts_rank=fts_rank,
            max_fts_rank=float(max_fts_rank),
            updated_at=note.updated_at,
            is_pinned=note.is_pinned,
            note_attachment_entity_ids=att_entity_ids,
            scoped_content_type_id=scoped_ct_id,
            scoped_object_id=scoped_object_id,
            note_tag_names=tag_names,
            query_tags=tags or [],
        )

        # Build attachment summaries
        attachment_names = []
        for att in note.attachments.all():
            display = att.attachment_display()
            if display:
                attachment_names.append(display)

        matched_in = _compute_matched_in(query_tokens, note) if query_tokens else []

        scored_results.append({
            "note_id": note.pk,
            "display_title": note.display_title,
            "url": note.get_absolute_url(),
            "headline": headline_val,
            "rank_score": fts_rank,
            "combined_score": scoring["combined_score"],
            "reasons": scoring["reasons"],
            "pinned": note.is_pinned,
            "updated_at": note.updated_at,
            "tags": tag_names,
            "attachments_summary": attachment_names,
            "matched_in": matched_in,
        })

    # Sort by combined_score descending
    scored_results.sort(key=lambda r: r["combined_score"], reverse=True)

    return {
        "query": query_str,
        "scope": scope,
        "results": scored_results[:limit],
    }


def _cos_fallback_results(base_qs, *, limit, scope, query_str, is_fallback=False):
    """
    Build fallback results: pinned notes first, then most recent.

    Used when query is blank or FTS returns no matches.
    """
    from .memory_scoring import score_fallback_note

    fallback_qs = base_qs.order_by("-is_pinned", "-updated_at")[:limit]
    results = []

    for note in fallback_qs:
        tag_names = [t.name for t in note.tags.all()]
        attachment_names = []
        for att in note.attachments.all():
            display = att.attachment_display()
            if display:
                attachment_names.append(display)

        scoring = score_fallback_note(
            updated_at=note.updated_at,
            is_pinned=note.is_pinned,
        )

        reasons = list(scoring["reasons"])
        if is_fallback:
            reasons.insert(0, "Fallback: no text matches found")

        results.append({
            "note_id": note.pk,
            "display_title": note.display_title,
            "url": note.get_absolute_url(),
            "headline": "",
            "rank_score": None,
            "combined_score": scoring["combined_score"],
            "reasons": reasons[:5],
            "pinned": note.is_pinned,
            "updated_at": note.updated_at,
            "tags": tag_names,
            "attachments_summary": attachment_names,
            "matched_in": [],
        })

    return {
        "query": query_str,
        "scope": scope,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Attachment index refresh helpers (Phase 4B.1)
# ---------------------------------------------------------------------------


def refresh_notes_for_entity(
    *,
    content_type_str,
    object_id,
    batch_size=500,
    dry_run=False,
):
    """
    Refresh attachments_text + search_vector for notes attached to a specific entity.

    Used by the management command and rename signals to keep attachment
    display strings current after entity renames.

    Args:
        content_type_str: "app_label.model" format (e.g. "life.project").
        object_id: Primary key of the entity.
        batch_size: Chunk size for processing (default 500).
        dry_run: If True, count only — do not write.

    Returns:
        dict with "notes_considered", "notes_updated".
    """
    parts = content_type_str.split(".")
    if len(parts) != 2:
        return {"notes_considered": 0, "notes_updated": 0}

    try:
        ct = ContentType.objects.get(app_label=parts[0], model=parts[1])
    except ContentType.DoesNotExist:
        return {"notes_considered": 0, "notes_updated": 0}

    note_ids = list(
        NoteAttachment.objects.filter(content_type=ct, object_id=object_id)
        .values_list("note_id", flat=True)
    )

    return _refresh_notes_by_ids(note_ids, batch_size=batch_size, dry_run=dry_run)


def refresh_notes_with_attachments(*, batch_size=500, dry_run=False):
    """
    Refresh attachments_text + search_vector for all notes that have attachments.

    Args:
        batch_size: Chunk size for processing (default 500).
        dry_run: If True, count only — do not write.

    Returns:
        dict with "notes_considered", "notes_updated".
    """
    note_ids = list(
        NoteAttachment.objects.values_list("note_id", flat=True).distinct()
    )

    return _refresh_notes_by_ids(note_ids, batch_size=batch_size, dry_run=dry_run)


def refresh_notes_for_content_type(*, content_type_str, batch_size=500, dry_run=False):
    """
    Refresh attachments_text + search_vector for notes attached to any entity
    of the given content type.

    Args:
        content_type_str: "app_label.model" format.
        batch_size: Chunk size for processing (default 500).
        dry_run: If True, count only — do not write.

    Returns:
        dict with "notes_considered", "notes_updated".
    """
    parts = content_type_str.split(".")
    if len(parts) != 2:
        return {"notes_considered": 0, "notes_updated": 0}

    try:
        ct = ContentType.objects.get(app_label=parts[0], model=parts[1])
    except ContentType.DoesNotExist:
        return {"notes_considered": 0, "notes_updated": 0}

    note_ids = list(
        NoteAttachment.objects.filter(content_type=ct)
        .values_list("note_id", flat=True)
        .distinct()
    )

    return _refresh_notes_by_ids(note_ids, batch_size=batch_size, dry_run=dry_run)


def _refresh_notes_by_ids(note_ids, *, batch_size=500, dry_run=False):
    """
    Internal helper: refresh attachments_text + search_vector for a list of note IDs.

    Processes in batches, prefetches attachments to avoid N+1.
    """
    total = len(note_ids)
    updated = 0

    if dry_run or total == 0:
        return {"notes_considered": total, "notes_updated": 0}

    for start in range(0, total, batch_size):
        batch_ids = note_ids[start : start + batch_size]
        notes = (
            Note.all_objects.filter(pk__in=batch_ids)
            .prefetch_related(
                Prefetch(
                    "attachments",
                    queryset=NoteAttachment.objects.select_related("content_type"),
                ),
            )
        )
        for note in notes:
            old_text = note.attachments_text
            note.rebuild_attachments_text()
            note.refresh_from_db(fields=["attachments_text"])
            if note.attachments_text != old_text:
                updated += 1
            # Always refresh search vector to ensure consistency
            note._refresh_search_vector()

    return {"notes_considered": total, "notes_updated": updated}


# ---------------------------------------------------------------------------
# Index integrity helpers (Phase 4B.2)
# ---------------------------------------------------------------------------


def find_notes_missing_attachments_text():
    """
    Find notes that have attachments but empty/null attachments_text.

    Returns a queryset of Note objects needing repair.
    """
    note_ids_with_attachments = (
        NoteAttachment.objects.values_list("note_id", flat=True).distinct()
    )
    return Note.all_objects.filter(
        pk__in=note_ids_with_attachments,
    ).filter(
        models.Q(attachments_text__isnull=True) | models.Q(attachments_text="")
    )


def find_notes_missing_search_vector():
    """
    Find notes where search_vector is null.

    Returns a queryset of Note objects needing repair.
    """
    return Note.all_objects.filter(search_vector__isnull=True)


def get_note_index_integrity_report():
    """
    Build a structured integrity report for the Notes index.

    Returns:
        dict with total_notes, notes_with_attachments,
        missing_attachments_text, missing_search_vector counts.
    """
    total_notes = Note.all_objects.count()
    notes_with_attachments = (
        NoteAttachment.objects.values_list("note_id", flat=True)
        .distinct()
        .count()
    )
    missing_attachments_text = find_notes_missing_attachments_text().count()
    missing_search_vector = find_notes_missing_search_vector().count()

    return {
        "total_notes": total_notes,
        "notes_with_attachments": notes_with_attachments,
        "missing_attachments_text": missing_attachments_text,
        "missing_search_vector": missing_search_vector,
    }


def repair_notes_missing_index(*, batch_size=500):
    """
    Repair all notes with missing index data.

    Fixes:
    - Notes with attachments but empty attachments_text
    - Notes with null search_vector

    Returns:
        dict with notes_repaired count.
    """
    repaired = 0

    # Fix notes missing attachments_text
    missing_att_ids = list(
        find_notes_missing_attachments_text().values_list("pk", flat=True)
    )
    if missing_att_ids:
        result = _refresh_notes_by_ids(missing_att_ids, batch_size=batch_size)
        repaired += result["notes_considered"]

    # Fix notes missing search_vector
    missing_sv_ids = list(
        find_notes_missing_search_vector()
        .exclude(pk__in=missing_att_ids)  # avoid double-processing
        .values_list("pk", flat=True)
    )
    if missing_sv_ids:
        for start in range(0, len(missing_sv_ids), batch_size):
            batch_ids = missing_sv_ids[start : start + batch_size]
            for note in Note.all_objects.filter(pk__in=batch_ids):
                note._refresh_search_vector()
            repaired += len(batch_ids)

    return {"notes_repaired": repaired}
