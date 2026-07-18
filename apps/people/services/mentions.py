"""Canonical mention reconciliation — the ONE writer of PersonMention truth.

A consumer (Journal, Tasks, …) hands us the source object + its saved rich-text HTML.
We extract the canonical Person IDs the editor's mention tokens carry and reconcile the
source object's PersonMention rows deterministically: create missing, keep valid, remove
stale, never duplicate. Ownership is enforced here (a token can only ever link a Person
the user owns). A resolved mention also grants People membership (a reference promotes a
Person into the everyday People experience).

HTML is the interaction artifact; PersonMention rows are the truth — never the reverse,
and never two writers.
"""
import re

from django.contrib.contenttypes.models import ContentType

from ..models import Person, PersonMembership, PersonMention
from .membership import grant_membership

# The sanitized mention markup: <span data-mention data-person-id="123">@Heather</span>
_MENTION_RE = re.compile(
    r'<span[^>]*data-person-id="(\d+)"[^>]*>@?([^<]*)</span>', re.IGNORECASE
)


def extract_mentions_from_html(html):
    """[(person_id, surface_text)] in document order, de-duplicated by id (first wins)."""
    out, seen = [], set()
    for m in _MENTION_RE.finditer(html or ""):
        pid = int(m.group(1))
        if pid not in seen:
            seen.add(pid)
            out.append((pid, (m.group(2) or "").strip()[:120]))
    return out


def reconcile_object_mentions(
    source_obj, html, user, *, source_type=PersonMention.Source.EXPLICIT_AT_MENTION
):
    """Reconcile PersonMention rows for ``source_obj`` from its saved ``html``.

    Deterministic + idempotent: re-saving unchanged HTML changes nothing. Returns an
    auditable summary. Never raises on a bad token — an unknown/foreign id is simply
    dropped (ownership boundary)."""
    ct = ContentType.objects.get_for_model(source_obj.__class__)
    oid = source_obj.pk

    wanted = extract_mentions_from_html(html)
    wanted_ids = [pid for pid, _ in wanted]
    surface_by_id = dict(wanted)

    # Ownership boundary — only Persons the user owns may ever be linked.
    valid_ids = set(
        Person.objects.filter(user=user, pk__in=wanted_ids).values_list("pk", flat=True)
    )

    existing = {
        m.person_id: m
        for m in PersonMention.objects.filter(content_type=ct, object_id=oid)
    }

    created = removed = 0
    for pid, mention in list(existing.items()):        # remove stale (token deleted)
        if pid not in valid_ids:
            mention.delete()
            removed += 1
    for pid in valid_ids:                              # create missing
        if pid not in existing:
            PersonMention.objects.create(
                person_id=pid, content_type=ct, object_id=oid,
                source_type=source_type, surface_text=surface_by_id.get(pid, ""),
            )
            created += 1
            person = Person.objects.get(pk=pid)        # a reference promotes to People
            if not PersonMembership.objects.filter(person=person).exists():
                grant_membership(person, PersonMembership.Grant.MENTION, actor="mention")

    return {"linked": len(valid_ids), "created": created, "removed": removed}


def mentions_for(source_obj):
    """Canonical Person mentions on a source object (for read/render surfaces)."""
    ct = ContentType.objects.get_for_model(source_obj.__class__)
    return (PersonMention.objects
            .filter(content_type=ct, object_id=source_obj.pk)
            .select_related("person"))
