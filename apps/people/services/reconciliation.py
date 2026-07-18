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
from ..normalization import compact_name, normalize_name
from .identity import create_person
from .membership import grant_membership
from .provenance import record_person_event

# Outcomes returned to the caller (auditable).
ALREADY_LINKED = "already_linked"
LINKED = "linked"
CREATED = "created"
REVIEW = "review"

# Match modes — how strongly a source row is reconciled to an existing canonical Person.
# The identity rule is deterministic and NEVER guesses: a single unambiguous match links;
# two-or-more distinct matches route to review; zero matches create a new canonical person.
#
#   EXACT_NAME     — full/display name only. The original Phase-0b behaviour; default so
#                    existing callers/tests are unchanged.
#   NAME_IDENTITY  — mirrors the canonical resolver's *identity* steps (exact full/display
#                    name → unique first name → compact/@handle form), so a bare-first-name
#                    source row ("Heather" from extraction) unifies with a full-name contact
#                    ("Heather Jenkins") FOR THE SAME USER. Used for living stores (A + C).
#                    Recognition roles/phrases are deliberately NOT consulted here — those
#                    are recognition, not identity-dedup.
#   SOURCE_LINK_ONLY — never match by name at all; link only via an existing PersonSourceLink
#                    (the idempotency check), else CREATE. Used for legacy genealogy (B),
#                    where same-name individuals are normal and merging by name is forbidden
#                    (GEDCOM identity = source_batch + xref, never name).
MATCH_EXACT_NAME = "exact_name"
MATCH_NAME_IDENTITY = "name_identity"
MATCH_SOURCE_LINK_ONLY = "source_link_only"


def _exact_matches(user, display_name, first_name, last_name):
    norm = normalize_name(display_name or f"{first_name} {last_name}")
    if not norm:
        return []
    unique = {}
    for p in Person.objects.filter(user=user):
        if normalize_name(p.display_name) == norm or normalize_name(p.full_name) == norm:
            unique[p.pk] = p
    return list(unique.values())


def _name_identity_matches(user, display_name, first_name, last_name):
    """The canonical resolver's identity steps, in order, for reconciliation dedup.

    Returns the set of canonical people matched at the FIRST step that matches — so a
    unique-first-name match is only considered when no full-name match exists. Never
    blends steps (that is how the resolver stays deterministic)."""
    people = list(Person.objects.filter(user=user))
    raw = display_name or f"{first_name} {last_name}"
    norm = normalize_name(raw)
    if not norm:
        return []

    # 1. exact full / display name.
    step = {p.pk: p for p in people
            if normalize_name(p.display_name) == norm or normalize_name(p.full_name) == norm}
    if step:
        return list(step.values())

    # 2. unique first name — ONLY when the SOURCE is a bare single token ("Heather").
    #    A full-name source ("Heather Smith") must NEVER match a different full name that
    #    merely shares a first name ("Heather Jenkins") — that would be merging on name
    #    alone. So a multi-token source skips this step entirely.
    is_bare_first_name = len(norm.split()) == 1
    if is_bare_first_name:
        step = {p.pk: p for p in people if normalize_name(p.first_name) == norm}
        if step:
            return list(step.values())

    # 3. compact / @handle form ("heatherjenkins").
    comp = compact_name(raw)
    if comp:
        step = {p.pk: p for p in people
                if compact_name(p.display_name) == comp or compact_name(p.full_name) == comp}
        if step:
            return list(step.values())

    return []


@transaction.atomic
def ingest_source_person(
    user, *, source_domain, source_pk,
    display_name="", first_name="", last_name="", email="", phone="",
    is_deceased=False, is_self=False, origin=PersonOrigin.MANUAL,
    membership_via=None, match_mode=MATCH_EXACT_NAME,
):
    """Bind one legacy source row to a canonical Person and return
    ``(person, outcome)``. Idempotent per (source_domain, source_pk).

    ``match_mode`` selects the identity-dedup strategy (see the MATCH_* constants).
    Regardless of mode, matching never guesses: one match links, two-or-more route to
    review, zero creates."""
    existing = PersonSourceLink.objects.filter(
        source_domain=source_domain, source_pk=source_pk
    ).first()
    if existing:
        return existing.person, ALREADY_LINKED

    if match_mode == MATCH_SOURCE_LINK_ONLY:
        matches = []                              # genealogy: never match by name
    elif match_mode == MATCH_NAME_IDENTITY:
        matches = _name_identity_matches(user, display_name, first_name, last_name)
    else:
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
