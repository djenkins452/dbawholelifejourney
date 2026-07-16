"""
Migration mapping / compatibility bridge — bind a legacy source Person row to a
canonical Person, WITHOUT redirecting consumers.

Feature-agnostic BY DESIGN: this module never imports relationships / legacy /
ai_relationships (the Core Person domain must not depend on a feature app). A
feature-side reader (a data migration or a per-module adapter) reads its own Person
table and calls `ingest_source_person(...)` with plain values. That keeps the
dependency direction correct and puts the feature-table reads in the migration
layer, not in Core.

Conservative reconciliation: auto-LINK only on an exact, unambiguous identity match;
route uncertain cases to review (a DUPLICATE_DETECTED event) — NEVER auto-merge by
guessing. The bridge (`PersonSourceLink`) is temporary and has an explicit retirement
gate: it is removed once every consumer reads the canonical Person.

Phase 0b establishes this MECHANISM (+ tests). The bulk backfill across production
data is deferred to the consumer-migration phases (0c/0d) — deliberately not run here.
"""

from django.db import transaction

from ..models import Person, PersonEvent, PersonMembership, PersonOrigin, PersonSourceLink
from ..normalization import normalize_name
from .identity import create_person
from .membership import grant_membership
from .provenance import record_person_event

# Outcomes returned to the caller (auditable).
ALREADY_LINKED = "already_linked"
LINKED = "linked"
CREATED = "created"
REVIEW = "review"


def _exact_matches(user, display_name, first_name, last_name):
    norm = normalize_name(display_name or f"{first_name} {last_name}")
    if not norm:
        return []
    unique = {}
    for p in Person.objects.filter(user=user):
        if normalize_name(p.display_name) == norm or normalize_name(p.full_name) == norm:
            unique[p.pk] = p
    return list(unique.values())


@transaction.atomic
def ingest_source_person(
    user, *, source_domain, source_pk,
    display_name="", first_name="", last_name="", email="", phone="",
    is_deceased=False, is_self=False, origin=PersonOrigin.MANUAL,
    membership_via=None,
):
    """Bind one legacy source row to a canonical Person and return
    ``(person, outcome)``. Idempotent per (source_domain, source_pk)."""
    existing = PersonSourceLink.objects.filter(
        source_domain=source_domain, source_pk=source_pk
    ).first()
    if existing:
        return existing.person, ALREADY_LINKED

    matches = _exact_matches(user, display_name, first_name, last_name)

    if len(matches) == 1:
        person = matches[0]
        _fill_blanks(person, email=email, phone=phone, first_name=first_name,
                     last_name=last_name, is_deceased=is_deceased, is_self=is_self)
        outcome = LINKED
    elif len(matches) > 1:
        # Ambiguous — do NOT guess. Create a distinct canonical person and flag it.
        person = create_person(
            user, origin=origin, actor="import", display_name=display_name,
            first_name=first_name, last_name=last_name, email=email, phone=phone,
            is_deceased=is_deceased, is_self=is_self,
        )
        record_person_event(
            person, PersonEvent.Type.DUPLICATE_DETECTED, actor="import",
            source_domain=source_domain, source_pk=source_pk,
            candidates=[p.pk for p in matches],
        )
        outcome = REVIEW
    else:
        person = create_person(
            user, origin=origin, actor="import", display_name=display_name,
            first_name=first_name, last_name=last_name, email=email, phone=phone,
            is_deceased=is_deceased, is_self=is_self,
        )
        outcome = CREATED

    PersonSourceLink.objects.create(
        person=person, source_domain=source_domain, source_pk=source_pk
    )
    if outcome == LINKED:
        record_person_event(
            person, PersonEvent.Type.SOURCE_ADDED, actor="import",
            source_domain=source_domain, source_pk=source_pk,
        )
    if membership_via:
        grant_membership(person, membership_via, actor="import")
    return person, outcome


def _fill_blanks(person, *, email, phone, first_name, last_name, is_deceased, is_self):
    """Never overwrite: only fill survivor blanks; OR-merge deceased/self truths."""
    fields = []
    for f, val in (("email", email), ("phone", phone),
                   ("first_name", first_name), ("last_name", last_name)):
        if not getattr(person, f) and val:
            setattr(person, f, val)
            fields.append(f)
    if is_deceased and not person.is_deceased:
        person.is_deceased = True
        fields.append("is_deceased")
    if is_self and not person.is_self:
        person.is_self = True
        fields.append("is_self")
    if fields:
        person.save(update_fields=list(set(fields)) + ["updated_at"])
